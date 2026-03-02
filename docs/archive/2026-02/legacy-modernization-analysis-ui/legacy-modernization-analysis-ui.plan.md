# Plan: Legacy Modernization 분석 시작 + 보고서 출력 WebUI

## 1. Overview

### 1.1 Feature Name
`legacy-modernization-analysis-ui`

### 1.2 Description
레거시 모더나이제이션 WebUI에서 "분석시작" 버튼 클릭 시 선택된 **제품(XSP/MSP/MVS/VOS3 등)의 전문 Agent**를 호출하여 소스코드 비호환성 분석을 수행하고, 분석 완료 후 **Agent별 보고서 템플릿** 기반으로 결과를 화면에 출력한다.

복수 파일이 선택된 경우, **전체 분석 결과 Summary**를 상단에 표시하고 개별 파일 상세 분석은 **Accordion(펼치기/닫기)** 방식으로 제공한다.

### 1.3 Motivation
- 현재 `LegacyModernizationPage.tsx`는 소스 입력 → 11-Agent 파이프라인 → 9종 보고서 조회 구조이나, **제품별 전문 Agent(legacy-xsp-expert 등)의 비호환성 분석 템플릿**이 활용되지 않음
- 현재 단일 파일만 분석 가능하며 복수 파일 일괄 분석/Summary 기능 없음
- OF7 소스 기반 Capability DB 검증 결과가 UI에 반영되지 않음

### 1.4 Scope
| In Scope | Out of Scope |
|----------|-------------|
| 제품 선택 → Agent 호출 연동 | 새로운 Agent 생성 (이미 존재) |
| 복수 파일 업로드/분석 | 파일 서버 저장 (세션 한정) |
| Summary + Accordion 보고서 UI | 보고서 PDF 다운로드 |
| SSE 스트리밍 진행률 | Agent 내부 로직 변경 |
| 비호환성 분석 템플릿 기반 렌더링 | 신규 Agent 타입 추가 |

## 2. Current State Analysis

### 2.1 Backend (이미 존재)

| 컴포넌트 | 파일 | 상태 |
|---------|------|------|
| Analysis Router | `app/api/legacy_modernization/routers/analysis.py` | POST /analyze, GET /status, GET /stream(SSE), GET /results |
| Analysis Service | `app/api/legacy_modernization/services/analysis_service.py` | 8-agent 파이프라인 오케스트레이션, 세션 관리 |
| Report Generator | `app/api/legacy_modernization/reports/generator.py` | 9종 보고서 (P0 5종 + P1 4종) |
| Schemas | `app/api/legacy_modernization/routers/schemas.py` | AnalysisRequest (단일 파일), AnalysisResponse |
| Capability Registry | `app/api/legacy_modernization/capabilities/registry.py` | 2,686+ 엔트리 (OF7 추출) |
| Compatibility Engine | `app/api/legacy_modernization/models/capability_model.py` | 4단계 패턴 매칭 |
| Parsers | `app/api/legacy_modernization/parsers/*.py` | COBOL, JCL, MAP, ASM 4종 |

### 2.2 Frontend (이미 존재)

| 컴포넌트 | 파일 | 상태 |
|---------|------|------|
| LegacyModernizationPage | `kms-portal-ui/src/pages/LegacyModernizationPage.tsx` | 단일 파일 분석, 파이프라인 진행률, 보고서 목록 |
| ModernizationAIAssistant | `kms-portal-ui/src/components/ModernizationAI/` | Floating chat panel (HOST/OF/ALL) |
| Legacy API Client | `kms-portal-ui/src/api/legacy.api.ts` | startAnalysis, getStatus, getResults, getProducts |
| i18n | `kms-portal-ui/src/i18n/locales/*/legacy.json` | 3개 언어 (en, ko, ja) |

### 2.3 Agent Templates (이미 존재)

| Agent | 파일 | 분석 템플릿 |
|-------|------|-----------|
| legacy-xsp-expert | `.claude/agents/legacy-xsp-expert.md` | XSP JCL 비호환성 분석 (OF7 파서 검증 + Capability DB) |
| legacy-jcl-expert | `.claude/agents/legacy-jcl-expert.md` | JCL Analysis Report (Step/Dataset/Feature) |
| legacy-cobol-expert | `.claude/agents/legacy-cobol-expert.md` | COBOL Analysis Report (Division/Feature/Migration) |
| legacy-asm-expert | `.claude/agents/legacy-asm-expert.md` | ASM 분석 보고서 |
| legacy-map-expert | `.claude/agents/legacy-map-expert.md` | MAP/BMS 분석 보고서 |

## 3. Requirements

### 3.1 Functional Requirements

#### FR-1: 제품 선택 기반 Agent 호출
- 사용자가 타겟 제품(XSP/MSP/MVS/VOS3 등)을 선택한 후 "분석시작" 클릭
- 선택된 제품에 해당하는 전문 Agent가 호출됨
- Agent는 OF7 Capability DB + 파서 소스 검증 기반 분석 수행

#### FR-2: 복수 파일 업로드/분석
- 여러 소스 파일을 동시에 업로드 가능
- 각 파일별로 독립적인 분석 세션 생성 (병렬 실행)
- 파일 목록 UI에서 각 파일의 분석 진행 상태 표시

#### FR-3: Summary 보고서 (복수 파일)
- 모든 파일 분석 완료 후 전체 Summary 자동 생성:
  - 총 파일 수, 총 기능 수, 지원률(%), 비호환 항목 수
  - 위험도별 집계 (HIGH/MEDIUM/LOW)
  - 비호환 항목 TOP-N 목록
- Summary는 보고서 상단에 고정 표시

#### FR-4: Accordion 상세 보고서
- 각 파일별 상세 분석 결과를 Accordion(접기/펼치기) 방식으로 표시
- Agent 템플릿 형식 유지 (파일 개요 → 파서 검증 → 라인별 분석 → 비호환 항목 → 권고사항)
- 기본 상태: 접힌 상태 (Summary만 보임)
- 클릭 시 펼쳐서 상세 내용 표시
- "모두 펼치기/접기" 토글 버튼

#### FR-5: SSE 스트리밍 진행률
- 기존 SSE 이벤트 스트림 활용 (`/analyze/{id}/stream`)
- 복수 파일 시 각 파일별 진행률 독립 표시
- 진행 중인 파일: 스피너 + 진행률(%)
- 완료된 파일: 체크 아이콘 + 결과 요약(지원률)
- 실패한 파일: X 아이콘 + 에러 메시지

### 3.2 Non-Functional Requirements

| 항목 | 요구사항 |
|------|---------|
| 응답 속도 | Summary 렌더링 < 200ms |
| 동시 분석 | 최대 10개 파일 병렬 분석 |
| i18n | 3개 언어 지원 (en, ko, ja) |
| 반응형 | 1024px 이상 지원 |

## 4. Implementation Plan

### Phase 1: Backend - 복수 파일 분석 API 확장

#### Step 1: BatchAnalysisRequest 스키마 추가
- **파일**: `app/api/legacy_modernization/routers/schemas.py`
- 추가:
  ```python
  class FileItem(BaseModel):
      file_name: str
      source_code: str

  class BatchAnalysisRequest(BaseModel):
      files: List[FileItem]     # 1~10개
      target_product: Optional[str]
      target_version: Optional[str]
      vendors: List[str] = ["openframe"]
      options: AnalysisOptions = AnalysisOptions()

  class BatchAnalysisResponse(BaseModel):
      batch_id: str
      analyses: List[AnalysisResponse]  # 각 파일별
      total_files: int
  ```

#### Step 2: Batch Analysis 엔드포인트
- **파일**: `app/api/legacy_modernization/routers/analysis.py`
- 추가: `POST /api/v1/legacy/analyze/batch`
- 각 파일마다 기존 `start_analysis()` 호출하여 병렬 세션 생성
- batch_id로 그룹핑

#### Step 3: Batch Status/Results 엔드포인트
- `GET /api/v1/legacy/analyze/batch/{batch_id}/status` — 전체 진행률
- `GET /api/v1/legacy/analyze/batch/{batch_id}/results` — 전체 결과 + Summary

#### Step 4: Summary 생성 로직
- **파일**: `app/api/legacy_modernization/services/analysis_service.py`
- `generate_batch_summary()` 메서드 추가
- 각 파일의 compatibility_findings 집계 → Summary 생성

### Phase 2: Backend - 제품별 Agent 템플릿 연동

#### Step 5: Agent 템플릿 레지스트리
- **파일**: `app/api/legacy_modernization/agents/template_registry.py` (신규)
- 제품별 분석 보고서 템플릿 매핑:
  ```python
  PRODUCT_AGENT_TEMPLATES = {
      "aim_xsp": "xsp_incompatibility_report",
      "batch": "jcl_analysis_report",
      "osc": "cobol_analysis_report",
      ...
  }
  ```
- 템플릿에 따른 보고서 섹션 구조 정의

#### Step 6: Capability DB 조회 결과를 보고서에 포함
- **파일**: `app/api/legacy_modernization/reports/generator.py`
- 기존 9종 보고서에 "Capability 검증 결과" 섹션 추가
- OF7 파서 소스 참조 정보 포함 (`source_ref` 필드)

### Phase 3: Frontend - 복수 파일 업로드 UI

#### Step 7: 다중 파일 업로드 컴포넌트
- **파일**: `kms-portal-ui/src/pages/LegacyModernizationPage.tsx` 수정
- 기존 단일 파일 입력 → 드래그앤드롭 + 파일 선택 (다중)
- 파일 목록 표시 (파일명, 타입 감지, 삭제 버튼)
- 최대 10개 제한

#### Step 8: 분석 시작 플로우 변경
- "분석시작" 클릭 → 복수 파일이면 Batch API 호출
- 단일 파일이면 기존 API 호출 (하위 호환)
- 각 파일별 SSE 스트림 구독

### Phase 4: Frontend - Summary + Accordion 보고서 UI

#### Step 9: AnalysisSummaryCard 컴포넌트 (신규)
- **파일**: `kms-portal-ui/src/components/ModernizationAI/AnalysisSummaryCard.tsx`
- 전체 Summary 카드:
  - 파일 수, 총 기능 수, 지원률, 비호환 수
  - 위험도별 배지 (HIGH: 빨강, MEDIUM: 노랑, LOW: 초록)
  - 비호환 TOP-5 항목 목록

#### Step 10: AnalysisAccordion 컴포넌트 (신규)
- **파일**: `kms-portal-ui/src/components/ModernizationAI/AnalysisAccordion.tsx`
- 각 파일별 Accordion 아이템:
  - 헤더: 파일명 + 지원률 배지 + 비호환 수 + 펼침/닫힘 아이콘
  - 본문: Agent 보고서 템플릿 렌더링 (Markdown → React)
- "모두 펼치기/접기" 토글 버튼

#### Step 11: 보고서 템플릿 렌더러
- **파일**: `kms-portal-ui/src/components/ModernizationAI/ReportRenderer.tsx`
- Agent 분석 보고서의 Markdown 테이블/리스트를 React 컴포넌트로 변환
- 섹션별 렌더링: 파일 개요, 파서 검증, 라인별 분석, 비호환 항목, 권고사항
- 판정 컬러코딩: OK=초록, WARNING=노랑, INCOMPATIBLE=빨강, SYNTAX_ERROR=보라

#### Step 12: i18n 번역 추가
- **파일**: `kms-portal-ui/src/i18n/locales/*/legacy.json` (3개 파일)
- 추가 키:
  - `legacy.analysis.summary.*` (Summary 관련)
  - `legacy.analysis.accordion.*` (Accordion 관련)
  - `legacy.analysis.verdict.*` (판정 관련)
  - `legacy.analysis.batchUpload.*` (복수 파일 관련)

### Phase 5: 통합 테스트

#### Step 13: E2E 테스트
- 단일 파일 분석 → 보고서 출력 확인
- 복수 파일(3개) 분석 → Summary + Accordion 확인
- XSP JCL 파일 분석 → XSP 전용 템플릿 렌더링 확인

## 5. Data Flow

```
[사용자]
  │
  ├─ 파일 업로드 (1~10개)
  ├─ 타겟 제품 선택 (aim_xsp, batch, osc 등)
  ├─ "분석시작" 클릭
  │
  ▼
[Frontend: LegacyModernizationPage]
  │
  ├─ files.length == 1 → POST /api/v1/legacy/analyze
  ├─ files.length > 1  → POST /api/v1/legacy/analyze/batch
  │
  ▼
[Backend: AnalysisService]
  │
  ├─ 파일별 AnalysisSession 생성
  ├─ OrchestratorAgent → 파서 → 전문 Agent → QA → Report
  ├─ Capability Registry 조회 (2,686+ 엔트리)
  ├─ SSE 이벤트 스트리밍 (status_change, completed)
  │
  ▼
[Backend: ReportGenerator]
  │
  ├─ 파일별 보고서 생성 (Agent 템플릿 기반)
  ├─ Batch Summary 생성 (복수 파일)
  │
  ▼
[Frontend: 결과 표시]
  │
  ├─ AnalysisSummaryCard (전체 요약)
  └─ AnalysisAccordion (파일별 상세)
      ├─ 파일1: [접기/펼치기] 파일 개요 → 파서 검증 → 라인별 분석 → 비호환 → 권고
      ├─ 파일2: [접기/펼치기] ...
      └─ 파일N: [접기/펼치기] ...
```

## 6. Files to Create/Modify

### New Files
| 파일 | 목적 |
|------|------|
| `app/api/legacy_modernization/agents/template_registry.py` | 제품별 Agent 보고서 템플릿 레지스트리 |
| `kms-portal-ui/src/components/ModernizationAI/AnalysisSummaryCard.tsx` | 전체 Summary 카드 |
| `kms-portal-ui/src/components/ModernizationAI/AnalysisAccordion.tsx` | 파일별 Accordion |
| `kms-portal-ui/src/components/ModernizationAI/ReportRenderer.tsx` | 보고서 템플릿 렌더러 |

### Modified Files
| 파일 | 변경 내용 |
|------|----------|
| `app/api/legacy_modernization/routers/schemas.py` | BatchAnalysisRequest/Response 추가 |
| `app/api/legacy_modernization/routers/analysis.py` | Batch 엔드포인트 3개 추가 |
| `app/api/legacy_modernization/services/analysis_service.py` | Batch 세션 관리 + Summary 생성 |
| `app/api/legacy_modernization/reports/generator.py` | Capability 검증 결과 섹션 추가 |
| `kms-portal-ui/src/pages/LegacyModernizationPage.tsx` | 복수 파일 + Batch 분석 플로우 |
| `kms-portal-ui/src/api/legacy.api.ts` | Batch API 클라이언트 함수 추가 |
| `kms-portal-ui/src/i18n/locales/en/legacy.json` | 영어 번역 추가 |
| `kms-portal-ui/src/i18n/locales/ko/legacy.json` | 한국어 번역 추가 |
| `kms-portal-ui/src/i18n/locales/ja/legacy.json` | 일본어 번역 추가 |

## 7. Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|------------|------------|
| 10개 파일 병렬 분석 시 메모리 부족 | HIGH | LOW | 동시 실행 제한 (semaphore), 순차 실행 fallback |
| Agent 템플릿 형식 불일치 | MEDIUM | MEDIUM | ReportRenderer에 fallback 렌더링 (plain markdown) |
| SSE 다중 연결 시 브라우저 제한 | MEDIUM | LOW | EventSource 대신 fetch + ReadableStream (이미 사용 중) |

## 8. Success Criteria

- [ ] 단일 파일 분석 → 제품별 Agent 템플릿 기반 보고서 정상 출력
- [ ] 3개 이상 복수 파일 → Summary 카드 + Accordion 정상 동작
- [ ] XSP JCL 분석 시 OF7 파서 검증 결과 표시
- [ ] 비호환 항목 색상 코딩 (OK/WARNING/INCOMPATIBLE) 정상
- [ ] i18n 3개 언어 모두 정상 표시
- [ ] Accordion 펼치기/접기 동작 정상
