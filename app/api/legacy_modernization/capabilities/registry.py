"""ProductRegistry — loads products.json + resolves capability inheritance chains.

Singleton service that provides:
- Product catalog listing (all products, by family, by asset_type)
- Version-specific capability resolution with inheritance
- Lookup methods for CompatibilityEngine integration
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Directory containing capability JSON files
_CAPABILITIES_DIR = Path(__file__).parent


class ProductVersion(BaseModel):
    """단일 제품 + 버전 정의."""

    product: str = Field(..., description="e.g., osc, aim_xsp")
    version: str = Field(..., description="e.g., 7.0, 7.1")
    display_name: str = Field(..., description="English display name")
    display_name_ko: str = Field("", description="Korean display name")
    display_name_ja: str = Field("", description="Japanese display name")
    asset_types: List[str] = Field(default_factory=list, description="Supported asset types")
    family: str = Field(..., description="Product family (e.g., AIM, OSC)")
    subtype: Optional[str] = Field(None, description="Subtype (e.g., XSP, MSP)")


class CapabilityRecord(BaseModel):
    """개별 capability 레코드 (JSON에서 로드)."""

    category: str
    pattern: str
    support: str  # "full", "partial", "workaround", "unsupported"
    notes: Optional[str] = None


class ResolvedCapabilities(BaseModel):
    """상속 체인이 해결된 최종 capability 세트."""

    product: str
    version: str
    capabilities: Dict[str, CapabilityRecord] = Field(
        default_factory=dict,
        description="pattern → CapabilityRecord (상속 후 override 적용)",
    )
    removed: List[str] = Field(default_factory=list, description="Removed patterns")


class ProductFamily(BaseModel):
    """프론트엔드용 제품군 그룹."""

    family: str
    display_name: str
    versions: List[ProductVersion]


class ProductRegistry:
    """제품 카탈로그 + 버전별 capability 레지스트리 (싱글턴).

    Initialization:
    1. Load products.json → product+version catalog
    2. Load _base.json → shared base capabilities
    3. Lazily resolve capability chains on first access
    """

    def __init__(self) -> None:
        self._products: List[ProductVersion] = []
        self._base_capabilities: List[CapabilityRecord] = []
        self._resolved_cache: Dict[str, ResolvedCapabilities] = {}
        self._loaded = False

    def load(self) -> None:
        """Load product catalog and base capabilities from disk."""
        if self._loaded:
            return

        # Load products.json
        products_path = _CAPABILITIES_DIR / "products.json"
        if products_path.exists():
            raw = json.loads(products_path.read_text(encoding="utf-8"))
            self._products = [ProductVersion(**p) for p in raw]
            logger.info("ProductRegistry: loaded %d product versions", len(self._products))
        else:
            logger.warning("ProductRegistry: products.json not found at %s", products_path)

        # Load _base.json
        base_path = _CAPABILITIES_DIR / "_base.json"
        if base_path.exists():
            raw = json.loads(base_path.read_text(encoding="utf-8"))
            self._base_capabilities = [
                CapabilityRecord(**c) for c in raw.get("capabilities", [])
            ]
            logger.info("ProductRegistry: loaded %d base capabilities", len(self._base_capabilities))

        self._loaded = True

    # ------------------------------------------------------------------
    # Catalog queries
    # ------------------------------------------------------------------

    def list_products(self) -> List[ProductVersion]:
        """전체 제품+버전 목록 반환."""
        self._ensure_loaded()
        return list(self._products)

    def list_families(self) -> List[ProductFamily]:
        """제품군별 그룹화된 목록 반환 (프론트엔드 트리 구조용)."""
        self._ensure_loaded()
        families: Dict[str, List[ProductVersion]] = {}
        for pv in self._products:
            key = pv.family
            if key not in families:
                families[key] = []
            families[key].append(pv)

        return [
            ProductFamily(
                family=fam,
                display_name=f"OpenFrame {fam}",
                versions=sorted(vers, key=lambda v: v.version),
            )
            for fam, vers in sorted(families.items())
        ]

    def get_product(self, product: str, version: str) -> Optional[ProductVersion]:
        """특정 제품+버전 조회."""
        self._ensure_loaded()
        for pv in self._products:
            if pv.product == product and pv.version == version:
                return pv
        return None

    def validate_product(self, product: str, version: str) -> bool:
        """제품+버전 존재 여부 검증."""
        return self.get_product(product, version) is not None

    def get_versions(self, product: str) -> List[str]:
        """특정 제품의 사용 가능한 버전 목록."""
        self._ensure_loaded()
        return sorted(
            pv.version for pv in self._products if pv.product == product
        )

    def filter_by_asset_type(self, asset_type: str) -> List[ProductVersion]:
        """특정 asset_type을 지원하는 제품만 필터링."""
        self._ensure_loaded()
        return [pv for pv in self._products if asset_type in pv.asset_types]

    # ------------------------------------------------------------------
    # Capability resolution (with inheritance)
    # ------------------------------------------------------------------

    def resolve_capabilities(self, product: str, version: str) -> ResolvedCapabilities:
        """버전별 capability 해결 (상속 체인 적용).

        Inheritance chain example:
            _base.json → osc/v7_0.json → osc/v7_1.json → osc/v7_3.json
        Later entries override earlier ones (same pattern key).
        """
        cache_key = f"{product}/{version}"
        if cache_key in self._resolved_cache:
            return self._resolved_cache[cache_key]

        self._ensure_loaded()

        # Start with base capabilities
        capabilities: Dict[str, CapabilityRecord] = {}
        for cap in self._base_capabilities:
            capabilities[cap.pattern] = cap

        # Build inheritance chain
        chain = self._build_chain(product, version)
        all_removed: List[str] = []

        for file_data in chain:
            # Apply capabilities (override existing)
            for cap_raw in file_data.get("capabilities", []):
                cap = CapabilityRecord(**cap_raw)
                capabilities[cap.pattern] = cap
            # Apply removals (items can be strings or dicts with "pattern" key)
            for item in file_data.get("removed", []):
                if isinstance(item, dict):
                    pattern = item.get("pattern", "")
                else:
                    pattern = item
                if pattern:
                    capabilities.pop(pattern, None)
                    all_removed.append(pattern)

        resolved = ResolvedCapabilities(
            product=product,
            version=version,
            capabilities=capabilities,
            removed=all_removed,
        )
        self._resolved_cache[cache_key] = resolved
        return resolved

    def lookup_capability(
        self, product: str, version: str, pattern: str,
    ) -> Optional[CapabilityRecord]:
        """특정 패턴의 capability 조회 (CompatibilityEngine 연동용)."""
        resolved = self.resolve_capabilities(product, version)
        return resolved.capabilities.get(pattern)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def _build_chain(self, product: str, version: str) -> List[Dict[str, Any]]:
        """상속 체인을 순서대로 빌드 (root → leaf)."""
        version_str = version.replace(".", "_")
        file_path = _CAPABILITIES_DIR / product / f"v{version_str}.json"

        if not file_path.exists():
            logger.warning("Capability file not found: %s", file_path)
            return []

        data = json.loads(file_path.read_text(encoding="utf-8"))

        # Resolve inheritance recursively
        inherits = data.get("inherits")
        if inherits:
            # inherits is like "osc/v7_0.json"
            parent_path = _CAPABILITIES_DIR / inherits
            if parent_path.exists():
                parent_data = json.loads(parent_path.read_text(encoding="utf-8"))
                parent_inherits = parent_data.get("inherits")

                # Recursively build ancestor chain
                ancestors = self._resolve_ancestors(parent_data, parent_path.parent)
                return ancestors + [data]
            else:
                logger.warning("Parent capability file not found: %s", parent_path)
                return [data]
        else:
            return [data]

    def _resolve_ancestors(
        self, data: Dict[str, Any], current_dir: Path,
    ) -> List[Dict[str, Any]]:
        """재귀적으로 조상 체인 해결."""
        inherits = data.get("inherits")
        if not inherits:
            return [data]

        parent_path = _CAPABILITIES_DIR / inherits
        if not parent_path.exists():
            logger.warning("Ancestor file not found: %s", parent_path)
            return [data]

        parent_data = json.loads(parent_path.read_text(encoding="utf-8"))
        ancestors = self._resolve_ancestors(parent_data, parent_path.parent)
        return ancestors + [data]


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_instance: Optional[ProductRegistry] = None


def get_product_registry() -> ProductRegistry:
    """Get or create the singleton ProductRegistry."""
    global _instance
    if _instance is None:
        _instance = ProductRegistry()
        _instance.load()
    return _instance
