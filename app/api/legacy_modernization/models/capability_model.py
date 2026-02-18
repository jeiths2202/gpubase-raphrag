"""Capability Model - OpenFrame compatibility database and mapping engine.

Provides CapabilityEntry lookup, CompatibilityFinding generation,
and multi-vendor comparison matrix construction.
"""

from datetime import datetime
from typing import ClassVar, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from ..parsers.base import NormalizedFeature, TraceEvidence
from .enums import (
    EffortLevel,
    FeatureCategory,
    Severity,
    SupportLevel,
)


class CapabilityEntry(BaseModel):
    """OpenFrame 기능 지원 항목"""

    feature_category: FeatureCategory
    feature_name: str = Field(..., description="e.g., EXEC CICS SEND MAP")
    support_level: SupportLevel
    openframe_version: str = Field(..., description="e.g., 7.1, 8.0")
    notes: Optional[str] = Field(None, description="부분 지원 시 상세 설명")
    workaround: Optional[str] = Field(None, description="우회 방안")
    migration_effort: EffortLevel


class CapabilityModel(BaseModel):
    """OpenFrame 호환성 데이터베이스"""

    vendor: str = "openframe"
    version: str
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    entries: List[CapabilityEntry] = Field(default_factory=list)

    def lookup(self, feature: NormalizedFeature) -> Optional[CapabilityEntry]:
        """Feature에 매칭되는 Capability 조회 (category + name 매칭)."""
        for entry in self.entries:
            if (
                entry.feature_category == feature.category
                and entry.feature_name == feature.name
            ):
                return entry
        return None


class CompatibilityFinding(BaseModel):
    """호환성 분석 결과 단위"""

    finding_id: str = Field(default_factory=lambda: str(uuid4()))
    feature: NormalizedFeature
    vendor: str
    vendor_version: str
    support_level: SupportLevel
    migration_effort: EffortLevel
    severity: Severity
    description: str
    recommendation: Optional[str] = None
    trace_evidence: Optional[TraceEvidence] = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)


# --- Vendor Comparison Matrix ---


class VendorComparisonRow(BaseModel):
    """벤더별 Feature 지원 비교 행."""

    feature: NormalizedFeature
    vendor_support: dict[str, SupportLevel]  # vendor → support_level
    best_vendor: str
    delta_notes: Optional[str] = None


class VendorComparisonSummary(BaseModel):
    """벤더 비교 요약."""

    vendor_scores: dict[str, float]  # vendor → overall_score (0-100)
    recommended_vendor: str
    recommendation_reason: str
    total_features: int
    supported_by_vendor: dict[str, int]
    unsupported_by_vendor: dict[str, int]


class VendorComparisonMatrix(BaseModel):
    """벤더별 호환성 비교 매트릭스"""

    asset_id: str
    vendors: List[str] = Field(
        default_factory=lambda: ["openframe", "ibm_zos", "micro_focus", "fujitsu_asp"]
    )
    feature_count: int = 0
    matrix: List[VendorComparisonRow] = Field(default_factory=list)
    summary: Optional[VendorComparisonSummary] = None


# --- Compatibility Engine ---

# SupportLevel → Severity mapping
_SUPPORT_TO_SEVERITY: dict[SupportLevel, Severity] = {
    SupportLevel.FULL: Severity.INFO,
    SupportLevel.PARTIAL: Severity.WARNING,
    SupportLevel.WORKAROUND: Severity.WARNING,
    SupportLevel.UNSUPPORTED: Severity.ERROR,
}

# SupportLevel → default EffortLevel
_SUPPORT_TO_EFFORT: dict[SupportLevel, EffortLevel] = {
    SupportLevel.FULL: EffortLevel.NONE,
    SupportLevel.PARTIAL: EffortLevel.MEDIUM,
    SupportLevel.WORKAROUND: EffortLevel.MEDIUM,
    SupportLevel.UNSUPPORTED: EffortLevel.HIGH,
}


class CompatibilityEngine:
    """Feature → Capability 매핑 엔진 (결정론적).

    No LLM calls — purely deterministic database lookup.
    Supports version-specific analysis via ProductRegistry.
    """

    def __init__(self, capability_models: dict[str, CapabilityModel]) -> None:
        self._models = capability_models

    async def analyze(
        self,
        features: List[NormalizedFeature],
        evidence: List[TraceEvidence],
        vendors: Optional[List[str]] = None,
        target_product: Optional[str] = None,
        target_version: Optional[str] = None,
    ) -> List[CompatibilityFinding]:
        """모든 feature × vendor 조합에 대해 Finding 생성.

        target_product/target_version이 지정되면 ProductRegistry에서
        버전별 capability를 조회하여 더 정확한 매칭을 수행합니다.
        """
        target_vendors = vendors or list(self._models.keys())
        findings: List[CompatibilityFinding] = []
        for feature in features:
            for vendor in target_vendors:
                # 버전별 매칭 우선 시도
                if target_product and target_version and vendor == "openframe":
                    finding = self._match_with_registry(
                        feature, target_product, target_version, evidence,
                    )
                    if finding:
                        findings.append(finding)
                        continue

                # 기존 CapabilityModel 기반 매칭 (fallback)
                model = self._models.get(vendor)
                if not model:
                    continue
                entry = model.lookup(feature)
                finding = self._create_finding(feature, entry, vendor, model.version, evidence)
                findings.append(finding)
        return findings

    def _match_with_registry(
        self,
        feature: NormalizedFeature,
        target_product: str,
        target_version: str,
        evidence: List[TraceEvidence],
    ) -> Optional[CompatibilityFinding]:
        """ProductRegistry를 통한 버전별 capability 매칭 (다단계).

        Matching strategies (in order):
        1. Direct pattern match via registry.lookup_capability()
        2. Utility program match: feature metadata has pgm → PGM=name
        3. JCL parameter match: category=jcl → JCL STMT PARAM
        """
        try:
            from ..capabilities.registry import get_product_registry
            registry = get_product_registry()

            # Strategy 1: Direct lookup (handles exact, prefix, param-level)
            cap = registry.lookup_capability(target_product, target_version, feature.name)

            # Strategy 2: Utility program match
            if cap is None and feature.metadata:
                pgm = feature.metadata.get("pgm") or feature.metadata.get("program")
                if pgm:
                    cap = registry.lookup_capability(
                        target_product, target_version, f"PGM={pgm.upper()}",
                    )

            # Strategy 3: JCL parameter with value
            if cap is None and feature.metadata:
                param = feature.metadata.get("param")
                value = feature.metadata.get("value")
                if param and value:
                    cap = registry.lookup_capability(
                        target_product, target_version, f"{feature.name}={value}",
                    )

            if cap is None:
                return None  # fallback to existing CapabilityModel

            support = SupportLevel(cap.support) if cap.support in [s.value for s in SupportLevel] else SupportLevel.UNSUPPORTED
            confidence = 0.95 if support == SupportLevel.FULL else 0.85
            if cap.source_ref:
                confidence = min(confidence + 0.03, 1.0)  # Boost for source-verified

            return CompatibilityFinding(
                finding_id=f"openframe-{feature.feature_id}-{support.value.upper()}",
                feature=feature,
                vendor="openframe",
                vendor_version=target_version,
                support_level=support,
                migration_effort=_SUPPORT_TO_EFFORT.get(support, EffortLevel.MEDIUM),
                severity=_SUPPORT_TO_SEVERITY.get(support, Severity.WARNING),
                description=cap.notes or f"Feature '{feature.name}' is {support.value} in {target_product} {target_version}",
                confidence=confidence,
                trace_evidence=self._find_evidence(feature, evidence),
            )
        except Exception:
            return None  # fallback to existing CapabilityModel

    def _create_finding(
        self,
        feature: NormalizedFeature,
        entry: Optional[CapabilityEntry],
        vendor: str,
        vendor_version: str,
        evidence: List[TraceEvidence],
    ) -> CompatibilityFinding:
        if entry is None:
            return CompatibilityFinding(
                finding_id=f"{vendor}-{feature.feature_id}-UNKNOWN",
                feature=feature,
                vendor=vendor,
                vendor_version=vendor_version,
                support_level=SupportLevel.UNSUPPORTED,
                migration_effort=EffortLevel.HIGH,
                severity=Severity.ERROR,
                description=f"Feature '{feature.name}' not found in {vendor} capability DB",
                confidence=0.5,
                trace_evidence=self._find_evidence(feature, evidence),
            )

        return CompatibilityFinding(
            finding_id=f"{vendor}-{feature.feature_id}-{entry.support_level.value.upper()}",
            feature=feature,
            vendor=vendor,
            vendor_version=entry.openframe_version,
            support_level=entry.support_level,
            migration_effort=entry.migration_effort,
            severity=_SUPPORT_TO_SEVERITY.get(entry.support_level, Severity.WARNING),
            description=entry.notes or f"Feature '{feature.name}' is {entry.support_level.value}",
            recommendation=entry.workaround,
            confidence=0.95 if entry.support_level == SupportLevel.FULL else 0.85,
            trace_evidence=self._find_evidence(feature, evidence),
        )

    @staticmethod
    def _find_evidence(
        feature: NormalizedFeature, evidence: List[TraceEvidence]
    ) -> Optional[TraceEvidence]:
        """Feature에 대응하는 TraceEvidence를 검색."""
        for ev in evidence:
            if feature.feature_id in ev.ast_node_path:
                return ev
        return None

    def build_comparison_matrix(
        self,
        asset_id: str,
        findings: List[CompatibilityFinding],
        vendors: Optional[List[str]] = None,
    ) -> VendorComparisonMatrix:
        """Finding 목록에서 벤더 비교 매트릭스 생성."""
        target_vendors = vendors or list(self._models.keys())

        # Group findings by feature_id
        feature_findings: dict[str, dict[str, CompatibilityFinding]] = {}
        features_by_id: dict[str, NormalizedFeature] = {}
        for f in findings:
            fid = f.feature.feature_id
            features_by_id[fid] = f.feature
            if fid not in feature_findings:
                feature_findings[fid] = {}
            feature_findings[fid][f.vendor] = f

        rows: List[VendorComparisonRow] = []
        for fid, vendor_map in feature_findings.items():
            vendor_support = {v: vendor_map[v].support_level for v in vendor_map}
            # Score: FULL=3, PARTIAL=2, WORKAROUND=1, UNSUPPORTED=0
            score_map = {
                SupportLevel.FULL: 3,
                SupportLevel.PARTIAL: 2,
                SupportLevel.WORKAROUND: 1,
                SupportLevel.UNSUPPORTED: 0,
            }
            best = max(vendor_support, key=lambda v: score_map.get(vendor_support[v], 0))
            rows.append(VendorComparisonRow(
                feature=features_by_id[fid],
                vendor_support=vendor_support,
                best_vendor=best,
            ))

        # Summary
        supported_count: dict[str, int] = {v: 0 for v in target_vendors}
        unsupported_count: dict[str, int] = {v: 0 for v in target_vendors}
        total_score: dict[str, float] = {v: 0.0 for v in target_vendors}

        for row in rows:
            for v, sl in row.vendor_support.items():
                if sl in (SupportLevel.FULL, SupportLevel.PARTIAL, SupportLevel.WORKAROUND):
                    supported_count[v] = supported_count.get(v, 0) + 1
                else:
                    unsupported_count[v] = unsupported_count.get(v, 0) + 1
                score_map_v = {
                    SupportLevel.FULL: 100,
                    SupportLevel.PARTIAL: 60,
                    SupportLevel.WORKAROUND: 40,
                    SupportLevel.UNSUPPORTED: 0,
                }
                total_score[v] = total_score.get(v, 0.0) + score_map_v.get(sl, 0)

        n = len(rows) or 1
        vendor_scores = {v: round(total_score[v] / n, 1) for v in target_vendors}
        recommended = max(vendor_scores, key=lambda v: vendor_scores[v]) if vendor_scores else target_vendors[0]

        summary = VendorComparisonSummary(
            vendor_scores=vendor_scores,
            recommended_vendor=recommended,
            recommendation_reason=f"Highest compatibility score: {vendor_scores.get(recommended, 0)}%",
            total_features=len(rows),
            supported_by_vendor=supported_count,
            unsupported_by_vendor=unsupported_count,
        )

        return VendorComparisonMatrix(
            asset_id=asset_id,
            vendors=target_vendors,
            feature_count=len(rows),
            matrix=rows,
            summary=summary,
        )
