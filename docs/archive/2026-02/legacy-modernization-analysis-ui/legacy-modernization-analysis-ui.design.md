# Design: Legacy Modernization 분석 시작 + 보고서 출력 WebUI

> **Plan 참조**: `docs/01-plan/features/legacy-modernization-analysis-ui.plan.md`

## 1. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│  Frontend (React + TypeScript)                                       │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ LegacyModernizationPage.tsx (수정)                               │ │
│  │  ┌───────────────────┐  ┌──────────────────────────────────┐   │ │
│  │  │ MultiFileUploader  │  │ AnalysisResultsPanel (신규)       │   │ │
│  │  │ - drag & drop      │  │  ┌──────────────────────────┐   │   │ │
│  │  │ - file list         │  │  │ BatchSummaryCard (신규)   │   │   │ │
│  │  │ - 10 file limit     │  │  └──────────────────────────┘   │   │ │
│  │  │ - analyze button    │  │  ┌──────────────────────────┐   │   │ │
│  │  └───────────────────┘  │  │ FileAccordion (신규)       │   │   │ │
│  │                          │  │  ├─ FileItem 1 ▼/▲        │   │   │ │
│  │                          │  │  │  └─ IncompatReport     │   │   │ │
│  │                          │  │  ├─ FileItem 2 ▼/▲        │   │   │ │
│  │                          │  │  └─ FileItem N ▼/▲        │   │   │ │
│  │                          │  └──────────────────────────┘   │   │ │
│  │                          └──────────────────────────────────┘   │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
         │                                   ▲
         │ POST /legacy/analyze/batch        │ GET /legacy/analyze/batch/{id}/results
         │ (files[], target_product)         │ SSE /legacy/analyze/batch/{id}/stream
         ▼                                   │
┌──────────────────────────────────────────────────────────────────────┐
│  Backend (FastAPI)                                                    │
│                                                                      │
│  analysis.py (수정)                                                   │
│    POST /analyze/batch  →  AnalysisService.start_batch_analysis()    │
│    GET  /analyze/batch/{id}/status                                    │
│    GET  /analyze/batch/{id}/stream   (SSE, file별 진행률)              │
│    GET  /analyze/batch/{id}/results  (Summary + 개별 결과)             │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │ AnalysisService (수정)                                       │     │
│  │  start_batch_analysis()                                      │     │
│  │   ├─ asyncio.gather(start_analysis(file1), ..., sem=3)       │     │
│  │   └─ BatchSession(batch_id, analysis_ids[])                  │     │
│  │  generate_batch_summary()                                    │     │
│  │   └─ aggregate findings across all files                     │     │
│  └─────────────────────────────────────────────────────────────┘     │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │ IncompatibilityReportBuilder (신규)                           │     │
│  │  - Capability DB 조회 → 지원/미지원 판별                       │     │
│  │  - 7-Section 보고서 구조 생성                                  │     │
│  │  - 위험도 집계 (HIGH/MEDIUM/LOW)                              │     │
│  └─────────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────┘
```

## 2. Data Models

### 2.1 Backend Schemas (`schemas.py` 추가)

```python
class FileItem(BaseModel):
    """개별 파일 정보."""
    file_name: str = Field(..., min_length=1, description="소스 파일명")
    source_code: str = Field(..., min_length=1, description="소스 코드 내용")

class BatchAnalysisRequest(BaseModel):
    """복수 파일 분석 요청."""
    files: List[FileItem] = Field(..., min_items=1, max_items=10,
                                  description="분석 대상 파일 목록 (1~10개)")
    target_product: Optional[str] = Field(None, description="타겟 OpenFrame 제품")
    target_version: Optional[str] = Field(None, description="타겟 제품 버전")
    vendors: List[str] = Field(default=["openframe"])
    options: AnalysisOptions = Field(default_factory=AnalysisOptions)

class FileAnalysisResult(BaseModel):
    """개별 파일 분석 결과."""
    file_name: str
    analysis_id: str
    status: str  # "completed" | "failed" | "in_progress"
    asset_type: str
    total_features: int = 0
    supported_count: int = 0
    incompatible_count: int = 0
    support_rate: float = 0.0  # 0.0 ~ 100.0
    risk_summary: Dict[str, int] = Field(default_factory=dict)  # {"HIGH": 1, "MEDIUM": 2, "LOW": 0}
    incompatibility_report: Optional[Dict[str, Any]] = None  # 7-Section 보고서

class BatchSummary(BaseModel):
    """전체 배치 분석 요약."""
    batch_id: str
    total_files: int
    completed_files: int
    failed_files: int
    total_features: int = 0
    total_supported: int = 0
    total_incompatible: int = 0
    overall_support_rate: float = 0.0
    risk_breakdown: Dict[str, int] = Field(default_factory=dict)
    top_incompatible_items: List[Dict[str, Any]] = Field(default_factory=list)

class BatchAnalysisResponse(BaseModel):
    """배치 분석 시작 응답."""
    batch_id: str
    total_files: int
    analysis_ids: List[str]
    status: str
    message: str

class BatchResultsResponse(BaseModel):
    """배치 분석 결과 응답."""
    batch_id: str
    summary: BatchSummary
    file_results: List[FileAnalysisResult]
```

### 2.2 IncompatibilityReport 구조 (7-Section)

```python
# incompatibility_report 필드의 JSON 구조
{
    "file_overview": {
        "file_name": "TESTJCL00",
        "format": "XSP JCL",
        "purpose": "FTP 데이터 전송",
        "program": "KEQEFT01",
        "total_lines": 16
    },
    "parser_verification": [
        {
            "statement": "JOB",
            "of7_token": "K_JOB",
            "stmt_type": "STMT_JOB",
            "support": "SUPPORTED"
        }
    ],
    "line_analysis": [
        {
            "line": 1,
            "source": "/EXPAN DEFINE HAIBNFTP,DAY=",
            "syntax_type": "macro_definition",
            "verdict": "OK"  # OK | WARNING | INCOMPATIBLE | SYNTAX_ERROR
        }
    ],
    "capability_lookup": [
        {
            "feature": "EXPAN/DEFEND",
            "capability_key": "jcl.expan",
            "status": "SUPPORTED",
            "notes": "OF7 parser supported"
        }
    ],
    "incompatible_items": [
        {
            "id": 1,
            "item": "&SCF.OPT09",
            "risk": "HIGH",
            "description": "Fujitsu SCF 시스템 변수",
            "mitigation": "JCL SET 문 또는 환경변수로 대체"
        }
    ],
    "recommendations": [
        "1. &SCF 변수를 OpenFrame 환경변수로 대체"
    ],
    "summary": {
        "total_features": 19,
        "supported": 18,
        "incompatible": 1,
        "support_rate": 94.7,
        "risk_high": 1,
        "risk_medium": 0,
        "risk_low": 0
    }
}
```

### 2.3 Frontend Types (`legacy.api.ts` 추가)

```typescript
export interface FileItem {
  file_name: string;
  source_code: string;
}

export interface BatchAnalysisRequest {
  files: FileItem[];
  target_product?: string;
  target_version?: string;
  vendors?: string[];
  options?: AnalysisOptions;
}

export interface BatchAnalysisResponse {
  batch_id: string;
  total_files: number;
  analysis_ids: string[];
  status: string;
  message: string;
}

export interface FileAnalysisResult {
  file_name: string;
  analysis_id: string;
  status: 'completed' | 'failed' | 'in_progress';
  asset_type: string;
  total_features: number;
  supported_count: number;
  incompatible_count: number;
  support_rate: number;
  risk_summary: Record<string, number>;
  incompatibility_report: IncompatibilityReport | null;
}

export interface IncompatibilityReport {
  file_overview: {
    file_name: string;
    format: string;
    purpose: string;
    program: string;
    total_lines: number;
  };
  parser_verification: Array<{
    statement: string;
    of7_token: string;
    stmt_type: string;
    support: 'SUPPORTED' | 'NOT_FOUND';
  }>;
  line_analysis: Array<{
    line: number;
    source: string;
    syntax_type: string;
    verdict: 'OK' | 'WARNING' | 'INCOMPATIBLE' | 'SYNTAX_ERROR';
  }>;
  capability_lookup: Array<{
    feature: string;
    capability_key: string;
    status: string;
    notes: string;
  }>;
  incompatible_items: Array<{
    id: number;
    item: string;
    risk: 'HIGH' | 'MEDIUM' | 'LOW';
    description: string;
    mitigation: string;
  }>;
  recommendations: string[];
  summary: {
    total_features: number;
    supported: number;
    incompatible: number;
    support_rate: number;
    risk_high: number;
    risk_medium: number;
    risk_low: number;
  };
}

export interface BatchSummary {
  batch_id: string;
  total_files: number;
  completed_files: number;
  failed_files: number;
  total_features: number;
  total_supported: number;
  total_incompatible: number;
  overall_support_rate: number;
  risk_breakdown: Record<string, number>;
  top_incompatible_items: Array<{
    file_name: string;
    item: string;
    risk: string;
    description: string;
  }>;
}

export interface BatchResultsResponse {
  batch_id: string;
  summary: BatchSummary;
  file_results: FileAnalysisResult[];
}

// SSE events for batch analysis
export interface BatchSSEEvent {
  event: 'file_started' | 'file_progress' | 'file_completed' | 'file_failed' | 'batch_completed';
  data: {
    batch_id: string;
    file_name?: string;
    analysis_id?: string;
    progress_percent?: number;
    current_agent?: string;
    status?: string;
    support_rate?: number;
    error?: string;
  };
}
```

## 3. API Endpoints Design

### 3.1 POST `/api/v1/legacy/analyze/batch`

```
Request:
  Body: BatchAnalysisRequest
Response:
  200: BatchAnalysisResponse { batch_id, total_files, analysis_ids[], status, message }
  400: Validation error (empty files, >10 files, invalid product)
```

### 3.2 GET `/api/v1/legacy/analyze/batch/{batch_id}/status`

```
Response:
  200: {
    batch_id: string,
    total_files: int,
    completed: int,
    failed: int,
    in_progress: int,
    overall_progress: float (0-100),
    file_statuses: [{file_name, status, progress_percent}]
  }
  404: Batch not found
```

### 3.3 GET `/api/v1/legacy/analyze/batch/{batch_id}/stream`

SSE 이벤트 스트림:

| Event | Trigger | Data |
|-------|---------|------|
| `file_started` | 파일 분석 시작 | `{file_name, analysis_id}` |
| `file_progress` | 파일 진행률 변경 | `{file_name, progress_percent, current_agent}` |
| `file_completed` | 파일 분석 완료 | `{file_name, support_rate, incompatible_count}` |
| `file_failed` | 파일 분석 실패 | `{file_name, error}` |
| `batch_completed` | 전체 완료 | `{total_files, completed, failed, overall_support_rate}` |

### 3.4 GET `/api/v1/legacy/analyze/batch/{batch_id}/results`

```
Response:
  200: BatchResultsResponse { summary, file_results[] }
  404: Batch not found
  425: Batch still in progress
```

## 4. Component Design

### 4.1 MultiFileUploader (LegacyModernizationPage.tsx 내 통합)

기존 단일 파일 textarea/upload → 복수 파일 지원으로 확장

```
┌──────────────────────────────────────────────────────┐
│  📁 Source Files                    [Upload] [Clear]  │
│ ┌──────────────────────────────────────────────────┐ │
│ │  Drop files here or click Upload                  │ │
│ │  Supported: .cob .cbl .jcl .map .bms .asm .s     │ │
│ └──────────────────────────────────────────────────┘ │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │ ☑ PAYROLL.cob   │ COBOL │ 245 lines │  [✕]   │  │
│  │ ☑ BATCH01.jcl   │ JCL   │  32 lines │  [✕]   │  │
│  │ ☑ SCREEN1.map   │ MAP   │  89 lines │  [✕]   │  │
│  └────────────────────────────────────────────────┘  │
│  3 files selected (366 lines total)  Max: 10 files   │
│                                                      │
│  Target: [OpenFrame ▾] [AIM/XSP ▾] [v7.3 ▾]        │
│                                                      │
│  [ ▶ Start Analysis ]                                │
└──────────────────────────────────────────────────────┘
```

**동작 방식**:
- 단일 파일: 기존 textarea 유지 (하위 호환)
- 복수 파일: `<input multiple>` + drag&drop → FileItem[] 구성
- 파일 추가 시 자동 타입 감지 + 라인 수 카운트
- 10파일 초과 시 경고 메시지
- "Start Analysis" 클릭 → 파일 1개면 기존 API, 2개 이상이면 Batch API

### 4.2 BatchSummaryCard

```
┌──────────────────────────────────────────────────────┐
│  📊 Analysis Summary                                  │
│ ─────────────────────────────────────────────────────│
│  Files: 3 completed / 3 total                        │
│  Features: 57 analyzed                               │
│  Support Rate: ████████████████░░ 89.5%              │
│  Incompatible: 6 items                               │
│                                                      │
│  Risk:  🔴 HIGH: 2  🟡 MEDIUM: 3  🟢 LOW: 1         │
│                                                      │
│  Top Issues:                                         │
│  1. &SCF.OPT09 - Fujitsu SCF system variable [HIGH] │
│  2. KEQEFT01 - Fujitsu FTP utility [HIGH]            │
│  3. Half-width Kana encoding [MEDIUM]                │
└──────────────────────────────────────────────────────┘
```

**Props**:
```typescript
interface BatchSummaryCardProps {
  summary: BatchSummary;
  isLoading?: boolean;
}
```

### 4.3 FileAccordion

```
┌──────────────────────────────────────────────────────┐
│  [Expand All] [Collapse All]                         │
│ ─────────────────────────────────────────────────────│
│  ▶ TESTJCL00  │ XSP JCL │ 94.7% │ 🔴1 🟡0 🟢0     │
│  ▼ TESTJCL01  │ XSP JCL │ 62.5% │ 🔴2 🟡1 🟢0     │  ← 펼침
│  ┌────────────────────────────────────────────────┐  │
│  │  1. 파일 개요                                   │  │
│  │  ┌─────────────────────────────────────┐       │  │
│  │  │ 파일명: TESTJCL01                    │       │  │
│  │  │ 형식: XSP JCL                        │       │  │
│  │  │ 목적: FTP 데이터 전송                 │       │  │
│  │  │ 프로그램: KEQEFT01                    │       │  │
│  │  └─────────────────────────────────────┘       │  │
│  │                                                │  │
│  │  2. 파서 검증 (OF7 소스 기반)                    │  │
│  │  ┌─────────┬──────────┬──────────┬──────────┐ │  │
│  │  │ 구문     │ OF7 Token│ STMT Type│ 지원     │ │  │
│  │  ├─────────┼──────────┼──────────┼──────────┤ │  │
│  │  │ JOB     │ K_JOB    │ STMT_JOB │ ✅       │ │  │
│  │  │ F1      │ K_ERROR  │ -        │ ❌       │ │  │
│  │  └─────────┴──────────┴──────────┴──────────┘ │  │
│  │                                                │  │
│  │  3. 라인별 분석                                  │  │
│  │  ... (verdict 컬러코딩: OK=🟢, WARN=🟡, ...)    │  │
│  │                                                │  │
│  │  4. 비호환 항목                                  │  │
│  │  ┌───┬────────────┬────┬──────────────────┐   │  │
│  │  │ # │ 항목        │위험│ 대응방안           │   │  │
│  │  ├───┼────────────┼────┼──────────────────┤   │  │
│  │  │ 1 │ &SCF.OPT09 │🔴  │ 환경변수 대체      │   │  │
│  │  │ 2 │ F1 구문     │🔴  │ FD로 수정          │   │  │
│  │  └───┴────────────┴────┴──────────────────┘   │  │
│  │                                                │  │
│  │  5. 요약: 지원 5/8 (62.5%)                      │  │
│  └────────────────────────────────────────────────┘  │
│  ▶ SCREEN1.map │ MAP │ 78.3% │ 🔴0 🟡2 🟢3         │
└──────────────────────────────────────────────────────┘
```

**Props**:
```typescript
interface FileAccordionProps {
  fileResults: FileAnalysisResult[];
  expandedFiles: Set<string>;   // 펼쳐진 파일명 Set
  onToggle: (fileName: string) => void;
  onExpandAll: () => void;
  onCollapseAll: () => void;
}
```

### 4.4 IncompatibilityReportView

7-Section 보고서를 React 컴포넌트로 렌더링.

**Props**:
```typescript
interface IncompatibilityReportViewProps {
  report: IncompatibilityReport;
}
```

**판정 컬러코딩**:
| Verdict | 배경색 | 텍스트 | 아이콘 |
|---------|--------|--------|--------|
| OK / SUPPORTED | `#dcfce7` (연두) | `#166534` | ✅ |
| WARNING | `#fef9c3` (연노랑) | `#854d0e` | ⚠️ |
| INCOMPATIBLE | `#fee2e2` (연분홍) | `#991b1b` | ❌ |
| SYNTAX_ERROR | `#ede9fe` (연보라) | `#5b21b6` | 🚫 |

## 5. Backend Implementation Details

### 5.1 BatchSession 클래스

```python
class BatchSession:
    """복수 파일 분석 배치 세션 관리."""

    def __init__(self, batch_id: str, file_names: List[str]) -> None:
        self.batch_id = batch_id
        self.file_names = file_names
        self.analysis_map: Dict[str, str] = {}  # file_name → analysis_id
        self.started_at = time.monotonic()
        self.created_at = datetime.utcnow()
```

### 5.2 start_batch_analysis() 로직

```python
async def start_batch_analysis(
    self,
    files: List[FileItem],
    tenant_id: str,
    target_product: Optional[str] = None,
    target_version: Optional[str] = None,
    vendors: Optional[List[str]] = None,
    options: Optional[dict] = None,
) -> Dict[str, Any]:
    batch_id = str(uuid4())
    batch = BatchSession(batch_id, [f.file_name for f in files])

    # 동시 실행 제한: semaphore(3)
    sem = asyncio.Semaphore(3)

    async def analyze_one(file_item: FileItem) -> str:
        async with sem:
            result = await self.start_analysis(
                file_name=file_item.file_name,
                source_code=file_item.source_code,
                tenant_id=tenant_id,
                target_product=target_product,
                target_version=target_version,
                vendors=vendors,
                options=options,
            )
            return result["analysis_id"]

    analysis_ids = await asyncio.gather(
        *[analyze_one(f) for f in files]
    )

    for fname, aid in zip([f.file_name for f in files], analysis_ids):
        batch.analysis_map[fname] = aid

    self._batches[batch_id] = batch
    return {
        "batch_id": batch_id,
        "total_files": len(files),
        "analysis_ids": list(analysis_ids),
        "status": "started",
        "message": f"Batch analysis started for {len(files)} files",
    }
```

### 5.3 generate_batch_summary() 로직

```python
async def generate_batch_summary(self, batch_id: str) -> BatchSummary:
    batch = self._batches[batch_id]
    all_results = []

    for fname, aid in batch.analysis_map.items():
        result = await self.get_results(aid)
        ws = result.get("workspace", {})
        findings = ws.get("compatibility_findings", [])
        features = ws.get("features", [])

        risk_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for f in findings:
            sev = f.get("severity", "info").upper()
            if sev in risk_counts:
                risk_counts[sev] += 1

        incompatible = len(findings)
        supported = len(features) - incompatible
        rate = (supported / max(len(features), 1)) * 100

        all_results.append({
            "file_name": fname,
            "total_features": len(features),
            "supported": max(supported, 0),
            "incompatible": incompatible,
            "support_rate": round(rate, 1),
            "risk": risk_counts,
            "findings": findings,
        })

    # Aggregate
    total_features = sum(r["total_features"] for r in all_results)
    total_supported = sum(r["supported"] for r in all_results)
    total_incompatible = sum(r["incompatible"] for r in all_results)
    overall_rate = (total_supported / max(total_features, 1)) * 100

    risk_total = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    all_incompatible_items = []
    for r in all_results:
        for k in risk_total:
            risk_total[k] += r["risk"].get(k, 0)
        for f in r["findings"]:
            all_incompatible_items.append({
                "file_name": r["file_name"],
                "item": f.get("feature", {}).get("name", "unknown"),
                "risk": f.get("severity", "info").upper(),
                "description": f.get("description", ""),
            })

    # Sort by risk priority
    risk_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    all_incompatible_items.sort(key=lambda x: risk_order.get(x["risk"], 3))

    return BatchSummary(
        batch_id=batch_id,
        total_files=len(all_results),
        completed_files=sum(1 for r in all_results if r["total_features"] > 0),
        failed_files=0,
        total_features=total_features,
        total_supported=total_supported,
        total_incompatible=total_incompatible,
        overall_support_rate=round(overall_rate, 1),
        risk_breakdown=risk_total,
        top_incompatible_items=all_incompatible_items[:10],
    )
```

### 5.4 IncompatibilityReportBuilder

```python
# 신규 파일: app/api/legacy_modernization/reports/incompatibility_builder.py

class IncompatibilityReportBuilder:
    """Capability DB + Parser 검증 결과를 7-Section 보고서로 조립."""

    def __init__(self) -> None:
        from ..capabilities.registry import get_product_registry
        self._registry = get_product_registry()

    async def build(
        self,
        workspace: SharedWorkspaceState,
    ) -> Dict[str, Any]:
        """SharedWorkspaceState에서 비호환성 보고서 생성."""
        features = workspace.features
        findings = workspace.compatibility_findings

        # Section 1: File Overview
        file_overview = {
            "file_name": workspace.file_name,
            "format": f"{workspace.asset_type.value.upper()}",
            "purpose": self._infer_purpose(workspace),
            "program": self._extract_program(workspace),
            "total_lines": workspace.loc_count,
        }

        # Section 2: Parser Verification
        parser_verification = self._build_parser_section(features)

        # Section 3: Line Analysis
        line_analysis = self._build_line_analysis(workspace)

        # Section 4: Capability DB Lookup
        capability_lookup = self._build_capability_section(
            features, workspace.target_product, workspace.target_version,
        )

        # Section 5: Incompatible Items
        incompatible_items = self._build_incompatible_items(findings)

        # Section 6: Recommendations
        recommendations = self._generate_recommendations(findings)

        # Section 7: Summary
        supported = len(features) - len(findings)
        rate = (supported / max(len(features), 1)) * 100
        risk_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for f in findings:
            sev = f.get("severity", "info").upper()
            if sev in risk_counts:
                risk_counts[sev] += 1

        summary = {
            "total_features": len(features),
            "supported": max(supported, 0),
            "incompatible": len(findings),
            "support_rate": round(rate, 1),
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
```

## 6. Frontend Implementation Details

### 6.1 State Management (LegacyModernizationPage.tsx 확장)

```typescript
// 기존 상태 유지 + 신규 batch 상태 추가
const [uploadedFiles, setUploadedFiles] = useState<FileItem[]>([]);
const [batchId, setBatchId] = useState<string | null>(null);
const [batchSummary, setBatchSummary] = useState<BatchSummary | null>(null);
const [fileResults, setFileResults] = useState<FileAnalysisResult[]>([]);
const [expandedFiles, setExpandedFiles] = useState<Set<string>>(new Set());
const [isBatchMode, setIsBatchMode] = useState(false);
```

### 6.2 분석 시작 플로우

```typescript
const handleAnalyze = async () => {
  if (uploadedFiles.length > 1) {
    // Batch mode
    setIsBatchMode(true);
    const response = await startBatchAnalysis({
      files: uploadedFiles,
      target_product: selectedProduct || undefined,
      target_version: selectedVersion || undefined,
      vendors: [vendor],
    });
    setBatchId(response.batch_id);
    subscribeBatchSSE(response.batch_id);
  } else if (uploadedFiles.length === 1) {
    // Single file mode (기존 로직)
    const file = uploadedFiles[0];
    setFileName(file.file_name);
    setSourceCode(file.source_code);
    // ... 기존 startAnalysis() 호출
  }
};
```

### 6.3 SSE 구독 (Batch)

```typescript
const subscribeBatchSSE = (batchId: string) => {
  const baseUrl = apiClient.defaults.baseURL || '/api/v1';
  const url = `${baseUrl}/legacy/analyze/batch/${batchId}/stream`;
  const eventSource = new EventSource(url, { withCredentials: true });

  eventSource.addEventListener('file_progress', (e: MessageEvent) => {
    const data = JSON.parse(e.data);
    setFileResults(prev =>
      prev.map(f =>
        f.file_name === data.file_name
          ? { ...f, status: 'in_progress' }
          : f
      )
    );
  });

  eventSource.addEventListener('file_completed', (e: MessageEvent) => {
    const data = JSON.parse(e.data);
    // Update specific file result
    setFileResults(prev =>
      prev.map(f =>
        f.file_name === data.file_name
          ? { ...f, status: 'completed', support_rate: data.support_rate }
          : f
      )
    );
  });

  eventSource.addEventListener('batch_completed', async (e: MessageEvent) => {
    eventSource.close();
    // Fetch full results
    const results = await getBatchResults(batchId);
    setBatchSummary(results.summary);
    setFileResults(results.file_results);
    setIsAnalyzing(false);
  });

  eventSource.onerror = () => eventSource.close();
};
```

## 7. i18n Keys

### 7.1 추가할 번역 키 (3개 언어)

```json
{
  "batch": {
    "uploadFiles": "Upload Files / 파일 업로드 / ファイルアップロード",
    "dropHere": "Drop files here / 여기에 파일을 드롭하세요 / ここにファイルをドロップ",
    "fileLimit": "Maximum 10 files / 최대 10개 파일 / 最大10ファイル",
    "filesSelected": "{count} files selected / {count}개 파일 선택 / {count}ファイル選択",
    "totalLines": "{count} lines total / 총 {count} 라인 / 合計{count}行",
    "clearFiles": "Clear All / 전체 삭제 / すべてクリア"
  },
  "summary": {
    "title": "Analysis Summary / 분석 요약 / 分析サマリー",
    "filesCompleted": "{completed}/{total} files completed",
    "featuresAnalyzed": "{count} features analyzed",
    "supportRate": "Support Rate / 지원률 / サポート率",
    "incompatibleItems": "Incompatible Items / 비호환 항목 / 非互換項目",
    "riskBreakdown": "Risk Breakdown / 위험도 분류 / リスク分類",
    "topIssues": "Top Issues / 주요 이슈 / 主要課題"
  },
  "accordion": {
    "expandAll": "Expand All / 모두 펼치기 / すべて展開",
    "collapseAll": "Collapse All / 모두 접기 / すべて折りたたむ"
  },
  "report": {
    "fileOverview": "File Overview / 파일 개요 / ファイル概要",
    "parserVerification": "Parser Verification / 파서 검증 / パーサ検証",
    "lineAnalysis": "Line Analysis / 라인별 분석 / 行別分析",
    "capabilityLookup": "Capability Lookup / 호환성 조회 / 互換性照会",
    "incompatibleFindings": "Incompatible Findings / 비호환 항목 / 非互換項目",
    "recommendations": "Recommendations / 권고사항 / 推奨事項",
    "analysisSummary": "Summary / 요약 / サマリー"
  },
  "verdict": {
    "ok": "OK / 지원 / OK",
    "warning": "Warning / 주의 / 注意",
    "incompatible": "Incompatible / 비호환 / 非互換",
    "syntaxError": "Syntax Error / 구문 오류 / 構文エラー",
    "supported": "Supported / 지원 / サポート",
    "notFound": "Not Found / 미확인 / 未確認"
  }
}
```

## 8. File List (Create/Modify)

### New Files (4)

| # | File | Purpose |
|---|------|---------|
| 1 | `app/api/legacy_modernization/reports/incompatibility_builder.py` | 7-Section 비호환성 보고서 빌더 |
| 2 | `kms-portal-ui/src/components/ModernizationAI/BatchSummaryCard.tsx` | Batch 분석 Summary 카드 |
| 3 | `kms-portal-ui/src/components/ModernizationAI/FileAccordion.tsx` | 파일별 Accordion + 보고서 렌더링 |
| 4 | `kms-portal-ui/src/components/ModernizationAI/IncompatibilityReportView.tsx` | 7-Section 보고서 렌더링 |

### Modified Files (8)

| # | File | Changes |
|---|------|---------|
| 1 | `app/api/legacy_modernization/routers/schemas.py` | FileItem, BatchAnalysisRequest/Response, BatchSummary, FileAnalysisResult 추가 |
| 2 | `app/api/legacy_modernization/routers/analysis.py` | POST /batch, GET /batch/{id}/status, GET /batch/{id}/stream, GET /batch/{id}/results |
| 3 | `app/api/legacy_modernization/services/analysis_service.py` | BatchSession, start_batch_analysis(), generate_batch_summary(), stream_batch_events() |
| 4 | `kms-portal-ui/src/pages/LegacyModernizationPage.tsx` | Multi-file upload, batch analysis flow, results panel |
| 5 | `kms-portal-ui/src/api/legacy.api.ts` | Batch types + API functions (startBatchAnalysis, getBatchStatus, getBatchResults) |
| 6 | `kms-portal-ui/src/i18n/locales/en/legacy.json` | batch, summary, accordion, report, verdict keys |
| 7 | `kms-portal-ui/src/i18n/locales/ko/legacy.json` | 한국어 번역 |
| 8 | `kms-portal-ui/src/i18n/locales/ja/legacy.json` | 일본어 번역 |

## 9. Implementation Order

```
Step 1: Backend schemas (schemas.py)
  ↓
Step 2: IncompatibilityReportBuilder (reports/incompatibility_builder.py)
  ↓
Step 3: BatchSession + AnalysisService 확장 (analysis_service.py)
  ↓
Step 4: Batch endpoints (analysis.py)
  ↓
Step 5: Frontend types + API client (legacy.api.ts)
  ↓
Step 6: BatchSummaryCard component
  ↓
Step 7: IncompatibilityReportView component
  ↓
Step 8: FileAccordion component
  ↓
Step 9: LegacyModernizationPage 통합 (multi-file upload + batch flow)
  ↓
Step 10: i18n (en, ko, ja)
```

## 10. Edge Cases & Error Handling

| Case | Handling |
|------|---------|
| 0 files uploaded | 분석 버튼 비활성화 |
| 11+ files | Upload 시 경고, 초과 파일 거부 |
| 파일 중 일부 실패 | 실패 파일은 status="failed"로 표시, 나머지 정상 처리 |
| 모든 파일 실패 | Summary에 failed_files=N, overall_support_rate=0 |
| SSE 연결 끊김 | Polling fallback (3초 간격) |
| Capability DB 항목 없음 | verdict="WARNING" (parser는 지원하나 DB 미확인) |
| 대용량 파일 (>10K lines) | 서버측 semaphore(3)로 동시 실행 제한 |
| 단일 파일 분석 | 기존 로직 그대로 사용 (하위 호환) |
