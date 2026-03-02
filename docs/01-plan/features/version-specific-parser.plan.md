# Version-Specific OpenFrame Parser Planning Document

> **Summary**: OpenFrame 제품을 버전별로 선택하여 해당 버전에 맞는 파서가 동작하도록 Legacy Modernization 분석 파이프라인 개선
>
> **Project**: HybridRAG KMS
> **Author**: Claude
> **Date**: 2026-02-18
> **Status**: Draft

---

## 1. Overview

### 1.1 Purpose

현재 Legacy Modernization 파이프라인은 COBOL/JCL/MAP/ASM 4개 자산 타입만 구분하며, OpenFrame 제품 및 버전 정보를 고려하지 않는다. 실제로 OpenFrame은 10개 제품군 × 다중 버전(총 25개 조합)으로 구성되며, 각 버전마다 지원하는 명령어/키워드/설정이 다르다.

사용자가 분석 대상 OpenFrame 제품+버전을 선택하면, 해당 버전의 지원 범위에 맞춰 파서가 호환성을 정확하게 판단할 수 있도록 개선한다.

### 1.2 Background

- 현재 `AssetType`은 `cobol`, `jcl`, `map`, `assembler` 4가지만 존재
- 파서는 언어 문법만 분석하며 타겟 OpenFrame 버전별 호환성 차이를 모름
- 예: `EXEC CICS` 명령은 OSC 7.0과 OSC 8.0에서 지원 범위가 다름
- 예: BATCH 7.0 vs 7.3에서 지원하는 JCL 유틸리티 프로그램이 다름
- 프론트엔드 벤더 드롭다운은 `openframe`/`microfocus`/`ibm` 수준으로만 구분

### 1.3 Related Documents

- 현재 구현: `app/api/legacy_modernization/` (11-agent pipeline)
- OF7 소스 참조: `OF7/base/`, `OF7/batch/`, `OF7/aim/`

---

## 2. Scope

### 2.1 In Scope

- [ ] OpenFrame 제품+버전 모델 정의 (10개 제품군 × 25개 조합)
- [ ] 제품+버전별 Capability Registry (지원 기능 목록) 구축
- [ ] API 스키마 확장: `target_product` + `target_version` 필드 추가
- [ ] 파서 결과에 버전별 호환성 매핑 (SupportLevel per feature)
- [ ] 프론트엔드 제품/버전 선택 UI (계층형 드롭다운)
- [ ] Domain Expert 에이전트가 버전별 Capability 참조하도록 개선

### 2.2 Out of Scope

- OF7 소스코드 자체의 정적 분석 (향후 Phase 2)
- 실제 컴파일/변환 실행
- 버전 간 자동 마이그레이션 코드 생성
- 3rd-party 벤더(Micro Focus, IBM) 버전별 지원 범위

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `OpenFrameProduct` enum 정의 (10개 제품군) | High | Pending |
| FR-02 | `ProductVersion` 모델 정의 (제품+버전 25개 조합) | High | Pending |
| FR-03 | 제품+버전별 Capability Registry 데이터 구조 설계 | High | Pending |
| FR-04 | API `AnalysisRequest`에 `target_product`, `target_version` 필드 추가 | High | Pending |
| FR-05 | 파서가 추출한 Feature를 Capability Registry와 대조하여 SupportLevel 부여 | High | Pending |
| FR-06 | 프론트엔드 제품/버전 2단계 선택 드롭다운 | Medium | Pending |
| FR-07 | 선택된 제품에 따라 적절한 Domain Expert Agent 자동 배정 | Medium | Pending |
| FR-08 | 보고서에 "버전별 지원 현황" 섹션 추가 | Medium | Pending |
| FR-09 | i18n 번역 (en, ko, ja) 제품/버전 라벨 | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | Capability Registry 로딩 < 100ms | 인메모리 캐시 |
| Extensibility | 새 버전 추가 시 코드 변경 없이 Registry 파일만 추가 | Registry JSON/YAML 분리 |
| Backward Compat | `target_product` 미지정 시 기존 동작 유지 | API 기본값 테스트 |

---

## 4. Target Products (25 Combinations)

### 4.1 Product Family Mapping

| Product Family | Sub-type | Versions | Asset Types |
|---------------|----------|----------|-------------|
| **AIM(XSP)** | XSP | 7.0, 7.1, 7.3 | COBOL, MAP |
| **AIM(MSP)** | MSP | 7.0, 7.1, 7.3 | COBOL, MAP |
| **OSC** | - | 7.0, 7.1, 7.3, 8.0 | COBOL (CICS) |
| **OSI** | - | 6.0, 7.0, 7.1 | COBOL (IMS) |
| **ASM** | - | 4.0 | ASM |
| **COBOL(OSVS)** | OSVS | 4.0 | COBOL |
| **COBOL(ENT)** | ENT | 4.0 | COBOL |
| **COBOL(MVS)** | MVS | 4.0 | COBOL |
| **BATCH** | - | 7.0, 7.1, 7.3 | JCL |
| **HiDB** | - | 3.0, 3.3, 7.2 | COBOL (IMS-DB) |
| **TACF** | - | 7.0, 7.1 | JCL, CONFIG |

### 4.2 Product → Parser Mapping

| Product | Primary Parser | Secondary Features |
|---------|---------------|-------------------|
| AIM(XSP/MSP) | COBOL + MAP | 트랜잭션 처리, 화면 맵 |
| OSC | COBOL | EXEC CICS 명령 호환성 |
| OSI | COBOL | IMS DL/I 호출 호환성 |
| ASM | ASM | 매크로, 레지스터, DSECT |
| COBOL(*) | COBOL | 방언별(OSVS/ENT/MVS) 문법 차이 |
| BATCH | JCL | JCL 유틸리티, 프로시저 |
| HiDB | COBOL | IMS DB 세그먼트, DL/I 호출 |
| TACF | JCL + CONFIG | 보안 리소스 정의 |

---

## 5. Data Model Design

### 5.1 OpenFrameProduct Enum

```python
class OpenFrameProduct(str, Enum):
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

### 5.2 ProductVersionSpec Model

```python
class ProductVersionSpec(BaseModel):
    product: OpenFrameProduct
    version: str          # "7.0", "7.1", etc.
    asset_types: List[AssetType]  # 지원하는 소스 타입
    display_name: str     # UI 표시 이름
    display_name_ja: str  # 일본어
    display_name_ko: str  # 한국어
```

### 5.3 Capability Registry Entry

```python
class CapabilityEntry(BaseModel):
    feature_category: FeatureCategory
    feature_pattern: str        # regex or keyword
    support_level: SupportLevel # full/partial/unsupported/workaround
    notes: Optional[str]        # 제한 사항 메모
    since_version: Optional[str]  # 도입 버전
    deprecated_version: Optional[str]  # 폐지 버전
```

### 5.4 Capability Registry Structure

```
app/api/legacy_modernization/
  capabilities/
    __init__.py
    registry.py          # CapabilityRegistry 서비스
    products.json        # 제품+버전 정의 (25개)
    osc/
      v7_0.json          # OSC 7.0 지원 기능 목록
      v7_1.json
      v7_3.json
      v8_0.json
    batch/
      v7_0.json
      v7_1.json
      v7_3.json
    ...
```

---

## 6. Architecture Considerations

### 6.1 Project Level

Enterprise (기존 Legacy Modernization 아키텍처 유지)

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| Registry 포맷 | JSON / YAML / Python dict | JSON | 비개발자도 편집 가능, 스키마 검증 용이 |
| Registry 로딩 | 시작 시 전체 로딩 / Lazy loading | 시작 시 전체 로딩 | 25개 조합, 데이터 소량 (<1MB) |
| 버전 비교 | semver / 문자열 비교 | 문자열 비교 | 버전이 1-2 depth (7.0, 7.1)로 단순 |
| 호환성 판정 위치 | Parser 내부 / 별도 서비스 | 별도 서비스 | 파서는 순수 구문 분석, 호환성은 분리 |
| API 하위 호환 | 필수 필드 / Optional 기본값 | Optional + 기본값 | `target_product` 미지정 시 기존 동작 |

### 6.3 Modified Architecture Flow

```
사용자 요청: { file_name, source_code, target_product: "osc", target_version: "7.3" }
    ↓
AnalysisService.start_analysis()
    ├─ _detect_asset_type(file_name) → COBOL
    ├─ CapabilityRegistry.get(product="osc", version="7.3")
    ↓
Orchestrator → COBOL Expert (with version context)
    ├─ COBOLParser.parse() → features[]  (순수 구문 분석)
    ├─ CapabilityMatcher.match(features, registry) → SupportLevel per feature
    ↓
LegacyKnowledgeAgent (with version-specific knowledge)
    ↓
CompetitorIntelligence → RiskAssessment → Review → QA → Reports
    ↓
보고서: "OSC 7.3 기준 호환성 분석 결과"
```

---

## 7. Implementation Plan

### Phase 1: Data Model + Registry (Backend)

1. `OpenFrameProduct` enum 추가 → `models/enums.py`
2. `ProductVersionSpec`, `CapabilityEntry` 모델 → `models/capability_model.py` 확장
3. `capabilities/` 디렉토리 + `registry.py` 서비스
4. 초기 Capability JSON 파일 생성 (25개 제품 버전)
5. `CapabilityRegistry` 싱글톤: `get_registry()` → 인메모리 로딩

### Phase 2: API + Service 확장

1. `AnalysisRequest`에 `target_product`, `target_version` 필드 추가
2. `AnalysisService.start_analysis()`에서 Registry 참조
3. `SharedWorkspaceState`에 `target_product`, `target_version` 필드 추가
4. `CapabilityMatcher` 서비스: Feature → SupportLevel 매칭

### Phase 3: Agent 개선

1. Domain Expert 에이전트에 버전 컨텍스트 전달
2. `LegacyKnowledgeAgent`가 Capability Registry 참조
3. `CompetitorIntelligence`에서 버전별 비교 포함
4. Report Generator에 "버전별 호환성" 섹션 추가

### Phase 4: Frontend

1. 제품군 → 버전 2단계 드롭다운 (기존 벤더 select 교체)
2. `legacy.api.ts` 타입 확장
3. i18n 제품명 번역 (en, ko, ja)
4. 파이프라인 상태에 제품/버전 정보 표시

---

## 8. Success Criteria

### 8.1 Definition of Done

- [ ] 25개 제품+버전 조합 모두 선택 가능
- [ ] 선택된 버전에 따라 호환성 판정 결과가 달라짐
- [ ] `target_product` 미지정 시 기존 동작 100% 유지 (하위 호환)
- [ ] 보고서에 "타겟 버전: OSC 7.3" 등 명시
- [ ] 프론트엔드에서 제품 → 버전 계층 선택 동작
- [ ] i18n 3개 언어 지원

### 8.2 Quality Criteria

- [ ] TypeScript 빌드 성공 (신규 코드 에러 없음)
- [ ] Capability Registry JSON 스키마 검증
- [ ] API 하위 호환성 테스트 (기존 요청 형식 동작)

---

## 9. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 제품별 Capability 데이터 부정확 | High | Medium | OF7 소스 + 공식 문서 교차 검증, 점진적 보강 |
| 25개 조합 초기 데이터 공백 | Medium | High | 공통 기능은 shared base로, 차이점만 override |
| Registry JSON 관리 복잡성 | Medium | Medium | 계층 구조: base → version override 패턴 |
| 기존 API 호환성 깨짐 | High | Low | Optional 필드 + 기본값으로 무변경 동작 보장 |

---

## 10. Next Steps

1. [ ] Design 문서 작성 (`/pdca design version-specific-parser`)
2. [ ] Capability Registry JSON 초기 데이터 구조 확정
3. [ ] 구현 시작

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-02-18 | Initial draft | Claude |
