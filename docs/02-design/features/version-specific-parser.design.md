# Version-Specific OpenFrame Parser Design Document

> **Feature**: version-specific-parser
> **Plan**: `docs/01-plan/features/version-specific-parser.plan.md`
> **Date**: 2026-02-18
> **Status**: Draft

---

## 1. Architecture Overview

### 1.1 Current State (AS-IS)

```
AnalysisRequest { file_name, source_code, vendors: ["openframe"] }
    ↓
_detect_asset_type(file_name) → AssetType (4: cobol/jcl/map/asm)
    ↓
Orchestrator → get_expert_for_asset(AssetType) → Expert Agent
    ↓
Parser.parse() → features[]
    ↓
CompatibilityEngine.analyze(features, vendors) → findings[]
    (vendor="openframe", version=단일값)
```

**문제점**:
- `AssetType`이 4개뿐 → OpenFrame 제품(11개)과 버전(25조합) 구분 불가
- `CapabilityModel.version`이 단일 문자열 → 버전별 차이 표현 불가
- `CompatibilityEngine`이 vendor 기준으로만 검색 → 같은 vendor 내 버전 비교 불가

### 1.2 Target State (TO-BE)

```
AnalysisRequest {
    file_name, source_code,
    target_product: "osc",        ← NEW (Optional)
    target_version: "7.3",        ← NEW (Optional)
    vendors: ["openframe"]
}
    ↓
_detect_asset_type(file_name) → AssetType (기존 유지)
    ↓
ProductRegistry.resolve(target_product, target_version)
    → ProductVersionSpec { product, version, asset_types, capabilities_ref }
    ↓
Orchestrator → Expert Agent (with version context)
    ↓
Parser.parse() → features[]  (변경 없음 - 순수 구문 분석)
    ↓
CapabilityMatcher.match(features, product_version_spec)
    → findings[] with version-specific SupportLevel
    ↓
Reports: "OSC 7.3 기준 호환성 분석"
```

---

## 2. Data Model Changes

### 2.1 New: `OpenFrameProduct` Enum

**File**: `app/api/legacy_modernization/models/enums.py` (추가)

```python
class OpenFrameProduct(str, Enum):
    """OpenFrame 제품군 (11개)"""
    AIM_XSP = "aim_xsp"
    AIM_MSP = "aim_msp"
    OSC = "osc"
    OSI = "osi"
    ASM = "asm"
    COBOL_OSVS = "cobol_osvs"
    COBOL_ENT = "cobol_ent"
    COBOL_MVS = "cobol_mvs"
    BATCH = "batch"
    HIDB = "hidb"
    TACF = "tacf"
```

### 2.2 New: Product Version Registry Data

**File**: `app/api/legacy_modernization/capabilities/products.json`

```json
[
  {
    "product": "aim_xsp",
    "version": "7.0",
    "display_name": "OpenFrame AIM(XSP) 7.0",
    "display_name_ko": "OpenFrame AIM(XSP) 7.0",
    "display_name_ja": "OpenFrame AIM(XSP) 7.0",
    "asset_types": ["cobol", "map"],
    "family": "AIM",
    "subtype": "XSP"
  },
  ...
]
```

25개 조합 전체를 하나의 JSON 파일로 관리 (경량, <5KB).

### 2.3 New: Capability JSON Files (per product-version)

**Directory**: `app/api/legacy_modernization/capabilities/{product}/`

```
capabilities/
  products.json              ← 제품+버전 목록 (25개)
  _base.json                 ← 공통 기능 (모든 버전 공유)
  osc/
    v7_0.json                ← OSC 7.0 전용 capability
    v7_1.json                ← OSC 7.1 (v7_0 + 추가)
    v7_3.json
    v8_0.json
  batch/
    v7_0.json
    v7_1.json
    v7_3.json
  aim_xsp/
    v7_0.json
    v7_1.json
    v7_3.json
  aim_msp/
    v7_0.json
    ...
  osi/
    v6_0.json
    v7_0.json
    v7_1.json
  asm/
    v4_0.json
  cobol_osvs/
    v4_0.json
  cobol_ent/
    v4_0.json
  cobol_mvs/
    v4_0.json
  hidb/
    v3_0.json
    v3_3.json
    v7_2.json
  tacf/
    v7_0.json
    v7_1.json
```

**Capability JSON 포맷**:

```json
{
  "product": "osc",
  "version": "7.3",
  "inherits": "osc/v7_1.json",
  "capabilities": [
    {
      "category": "cics",
      "pattern": "EXEC CICS SEND MAP",
      "support": "full",
      "notes": null
    },
    {
      "category": "cics",
      "pattern": "EXEC CICS LINK",
      "support": "full",
      "notes": null
    },
    {
      "category": "cics",
      "pattern": "EXEC CICS WEB",
      "support": "partial",
      "notes": "SEND/RECEIVE만 지원, CONVERSE 미지원"
    }
  ],
  "removed": [
    {
      "category": "cics",
      "pattern": "EXEC CICS FEPI",
      "reason": "deprecated in 7.3"
    }
  ]
}
```

**상속 구조**: `inherits` 필드로 이전 버전의 capability를 상속받고, 추가/수정/삭제만 기록.

```
_base.json → osc/v7_0.json → osc/v7_1.json → osc/v7_3.json → osc/v8_0.json
```

### 2.4 Modified: `SharedWorkspaceState`

**File**: `app/api/legacy_modernization/core/shared_state.py` (2개 필드 추가)

```python
class SharedWorkspaceState(BaseModel):
    # ... existing fields ...

    # === NEW: Target product context ===
    target_product: Optional[str] = None    # "osc", "batch", etc.
    target_version: Optional[str] = None    # "7.3", "4.0", etc.
```

`WritePermission`에 Orchestrator 권한 추가:

```python
AgentRole.ORCHESTRATOR: {
    ...,
    "target_product", "target_version",  # NEW
},
```

### 2.5 Modified: `AnalysisRequest` Schema

**File**: `app/api/legacy_modernization/routers/schemas.py`

```python
class AnalysisRequest(BaseModel):
    file_name: str = Field(...)
    source_code: str = Field(...)
    vendors: List[str] = Field(default=["openframe"])
    options: AnalysisOptions = Field(default_factory=AnalysisOptions)

    # NEW: Optional product/version targeting
    target_product: Optional[str] = Field(
        None,
        description="OpenFrame product (e.g., 'osc', 'batch', 'aim_xsp')",
        examples=["osc", "batch", "aim_xsp"],
    )
    target_version: Optional[str] = Field(
        None,
        description="Product version (e.g., '7.3', '4.0')",
        examples=["7.3", "7.0", "4.0"],
    )
```

**하위 호환성**: 두 필드 모두 `Optional` → 기존 API 요청은 변경 없이 동작.

---

## 3. New Service: `ProductRegistry`

**File**: `app/api/legacy_modernization/capabilities/registry.py`

### 3.1 Class Design

```python
class ProductVersionSpec(BaseModel):
    product: str              # "osc"
    version: str              # "7.3"
    display_name: str
    display_name_ko: str
    display_name_ja: str
    asset_types: List[str]    # ["cobol"]
    family: str               # "OSC"
    subtype: Optional[str]    # "XSP", "MSP", None

class ResolvedCapability(BaseModel):
    category: str             # FeatureCategory value
    pattern: str              # "EXEC CICS SEND MAP"
    support: str              # SupportLevel value
    notes: Optional[str]

class ProductRegistry:
    """제품+버전별 Capability를 인메모리 로딩+캐시하는 싱글톤."""

    _instance: Optional["ProductRegistry"] = None

    def __init__(self, base_dir: Path):
        self._base_dir = base_dir
        self._products: Dict[str, ProductVersionSpec] = {}  # key: "osc:7.3"
        self._capabilities: Dict[str, List[ResolvedCapability]] = {}

    @classmethod
    def get_instance(cls) -> "ProductRegistry":
        if cls._instance is None:
            base = Path(__file__).parent
            cls._instance = cls(base)
            cls._instance.load()
        return cls._instance

    def load(self) -> None:
        """products.json 로딩 + 각 버전별 capability 파일 로딩"""

    def list_products(self) -> List[ProductVersionSpec]:
        """25개 전체 반환 (프론트엔드 드롭다운용)"""

    def list_families(self) -> List[dict]:
        """제품군별 그룹핑: [{"family":"OSC","versions":["7.0","7.1",...]}]"""

    def get_spec(self, product: str, version: str) -> Optional[ProductVersionSpec]:
        """특정 제품+버전 조회"""

    def get_capabilities(self, product: str, version: str) -> List[ResolvedCapability]:
        """상속 체인 resolve 후 최종 capability 목록 반환"""

    def validate_combination(self, product: str, version: str) -> bool:
        """유효한 조합인지 검증"""
```

### 3.2 Capability Inheritance Resolution

```
load("osc", "7.3"):
  1. _base.json 로딩 → base_caps[]
  2. osc/v7_0.json 로딩 → inherits 없음 → merge(base_caps, v7_0)
  3. osc/v7_1.json 로딩 → inherits: osc/v7_0 → merge(v7_0_resolved, v7_1)
  4. osc/v7_3.json 로딩 → inherits: osc/v7_1 → merge(v7_1_resolved, v7_3)
  5. removed[] 항목 제거
  → 최종: osc:7.3 resolved capabilities
```

---

## 4. Service Layer Changes

### 4.1 `AnalysisService.start_analysis()` 수정

**File**: `app/api/legacy_modernization/services/analysis_service.py`

```python
async def start_analysis(
    self,
    file_name: str,
    source_code: str,
    tenant_id: str,
    vendors: Optional[List[str]] = None,
    options: Optional[dict] = None,
    target_product: Optional[str] = None,      # NEW
    target_version: Optional[str] = None,       # NEW
) -> Dict[str, Any]:
    ...
    # Validate product+version combination
    if target_product and target_version:
        registry = ProductRegistry.get_instance()
        if not registry.validate_combination(target_product, target_version):
            raise ValueError(f"Invalid combination: {target_product} {target_version}")

    # Store in workspace
    workspace.target_product = target_product
    workspace.target_version = target_version
    ...
```

### 4.2 `CompatibilityEngine` 확장

**File**: `app/api/legacy_modernization/models/capability_model.py`

기존 `CompatibilityEngine.analyze()`에 `ProductRegistry` 연동:

```python
async def analyze(
    self,
    features: List[NormalizedFeature],
    evidence: List[TraceEvidence],
    vendors: Optional[List[str]] = None,
    target_product: Optional[str] = None,       # NEW
    target_version: Optional[str] = None,        # NEW
) -> List[CompatibilityFinding]:
    if target_product and target_version:
        # Version-specific lookup from registry
        registry = ProductRegistry.get_instance()
        caps = registry.get_capabilities(target_product, target_version)
        return self._match_with_registry(features, evidence, caps, target_product, target_version)
    else:
        # Legacy behavior: use existing CapabilityModel dict
        return self._legacy_analyze(features, evidence, vendors)
```

---

## 5. API Endpoint Changes

### 5.1 Modified: `POST /api/v1/legacy/analyze`

Request body에 `target_product`, `target_version` 추가 (Optional).

### 5.2 New: `GET /api/v1/legacy/products`

프론트엔드 드롭다운용 제품 목록 API:

```python
@router.get("/legacy/products")
async def list_products():
    registry = ProductRegistry.get_instance()
    families = registry.list_families()
    return {"families": families}
```

Response:
```json
{
  "families": [
    {
      "family": "AIM",
      "products": [
        {
          "product": "aim_xsp",
          "subtype": "XSP",
          "versions": [
            {"version": "7.0", "display_name": "OpenFrame AIM(XSP) 7.0"},
            {"version": "7.1", "display_name": "OpenFrame AIM(XSP) 7.1"},
            {"version": "7.3", "display_name": "OpenFrame AIM(XSP) 7.3"}
          ]
        },
        {
          "product": "aim_msp",
          "subtype": "MSP",
          "versions": [...]
        }
      ]
    },
    {
      "family": "OSC",
      "products": [
        {
          "product": "osc",
          "subtype": null,
          "versions": [
            {"version": "7.0", ...},
            {"version": "7.1", ...},
            {"version": "7.3", ...},
            {"version": "8.0", ...}
          ]
        }
      ]
    },
    ...
  ]
}
```

---

## 6. Frontend Changes

### 6.1 API Type Extensions

**File**: `kms-portal-ui/src/api/legacy.api.ts`

```typescript
// NEW types
export interface ProductFamily {
  family: string;
  products: ProductInfo[];
}
export interface ProductInfo {
  product: string;
  subtype: string | null;
  versions: ProductVersionInfo[];
}
export interface ProductVersionInfo {
  version: string;
  display_name: string;
}

// Modified request
export interface AnalysisRequest {
  file_name: string;
  source_code: string;
  vendors?: string[];
  target_product?: string;   // NEW
  target_version?: string;   // NEW
}

// NEW API function
export const getProducts = async (): Promise<{ families: ProductFamily[] }> => {
  const response = await apiClient.get('/legacy/products');
  return response.data;
};
```

### 6.2 UI: Product/Version Selector

**File**: `kms-portal-ui/src/pages/LegacyModernizationPage.tsx`

기존 벤더 `<select>` 를 **제품군 → 제품 → 버전** 3단계 선택으로 교체:

```
┌─────────────────────────────────────────────────────────┐
│ 타겟 제품:  [OSC          ▼]  버전: [7.3    ▼]         │
│                                                         │
│  AIM(XSP)  AIM(MSP)  OSC  OSI  ASM  COBOL  BATCH ...  │
└─────────────────────────────────────────────────────────┘
```

State 변경:
```typescript
// Before
const [vendor, setVendor] = useState('openframe');

// After
const [targetProduct, setTargetProduct] = useState<string | null>(null);
const [targetVersion, setTargetVersion] = useState<string | null>(null);
const [productFamilies, setProductFamilies] = useState<ProductFamily[]>([]);
```

`useEffect`로 컴포넌트 마운트 시 `getProducts()` 호출하여 드롭다운 데이터 로딩.

### 6.3 i18n Additions

**3개 locale 모두** `legacy.json`에 추가:

```json
{
  "targetProduct": "Target Product",
  "targetVersion": "Version",
  "selectProduct": "Select product...",
  "selectVersion": "Select version...",
  "allVersions": "All versions (generic)"
}
```

---

## 7. Implementation Order

| Step | File(s) | Description | Depends |
|------|---------|-------------|---------|
| 1 | `models/enums.py` | `OpenFrameProduct` enum 추가 | - |
| 2 | `capabilities/products.json` | 25개 제품+버전 정의 | Step 1 |
| 3 | `capabilities/_base.json` | 공통 capability 정의 | - |
| 4 | `capabilities/{product}/v*.json` | 제품별 capability JSON (25개) | Step 3 |
| 5 | `capabilities/registry.py` | `ProductRegistry` 서비스 | Steps 2,4 |
| 6 | `core/shared_state.py` | `target_product`, `target_version` 필드 + ACL | Step 1 |
| 7 | `routers/schemas.py` | `AnalysisRequest` 확장 | Step 1 |
| 8 | `services/analysis_service.py` | Registry 연동 + validation | Steps 5,6 |
| 9 | `models/capability_model.py` | `CompatibilityEngine` 확장 | Step 5 |
| 10 | `routers/analysis.py` | `GET /products` + `POST /analyze` 수정 | Steps 7,8 |
| 11 | `legacy.api.ts` | 프론트엔드 API 타입+함수 | Step 10 |
| 12 | `LegacyModernizationPage.tsx` | 제품/버전 선택 UI | Step 11 |
| 13 | `i18n locales` | en/ko/ja 번역 추가 | Step 12 |

---

## 8. Backward Compatibility

| Scenario | Expected Behavior |
|----------|------------------|
| `target_product` 미지정 | 기존과 동일: AssetType 기반 범용 분석 |
| `target_product`만 지정, `target_version` 없음 | 해당 제품의 최신 버전으로 자동 선택 |
| 잘못된 조합 (e.g., `osc` + `4.0`) | 400 Bad Request with validation error |
| 프론트엔드 미선택 상태 | `target_product=null` → 기존 동작 |

---

## 9. Test Strategy

| Test Type | Coverage |
|-----------|----------|
| Unit: `ProductRegistry.load()` | 25개 조합 로딩, 상속 체인 해소 검증 |
| Unit: `CapabilityMatcher` | Feature → SupportLevel 매핑 정확도 |
| Integration: `POST /analyze` | `target_product`+`target_version` 전달 → workspace에 저장 확인 |
| Integration: `GET /products` | 응답 구조 검증, 25개 조합 포함 |
| E2E: Frontend | 드롭다운 선택 → 분석 요청 → 결과에 버전 정보 표시 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-02-18 | Initial design | Claude |
