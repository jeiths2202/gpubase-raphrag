# Plan: JCL Diagnosis Frontend Viewer

> **Feature**: `jcl-diagnosis-frontend-viewer`
> **Created**: 2026-02-25
> **Priority**: High
> **Level**: Enterprise
> **Depends On**: `jcl-diagnosis-report-template` (backend, archived 100%)

---

## Context

The JCL Diagnosis backend (5-agent pipeline) is fully implemented:
- `POST /api/v1/jcl-diagnosis/analyze` — zip upload → SSE streaming diagnosis
- `GET /api/v1/jcl-diagnosis/{diagnosis_id}/report` — self-contained HTML report
- 11 SSE event types with structured JSON payloads
- In-memory report cache (1-hour TTL)

**No frontend exists yet.** Users cannot access the JCL diagnosis feature from the KMS portal.

**Goal**: Build a React page that lets users upload a JOB output zip file, watch the 5-agent pipeline progress in real-time via SSE, and view/download the final HTML diagnosis report.

---

## Architecture

```
[User uploads .zip]
    ↓
  JCLDiagnosisPage.tsx
    ↓ multipart/form-data POST
  fetch('/api/v1/jcl-diagnosis/analyze')
    ↓ SSE stream
  Event handler (switch on event.type)
    ├─ file_extracted     → ProgressBar: "Extracting..."
    ├─ file_classified    → FileList: show classified files
    ├─ jcl_parsed         → JobInfo: show JOB name + steps
    ├─ step_flow          → StepFlow: visual pipeline
    ├─ error_found        → ErrorCard: error code + severity badge
    ├─ searching_knowledge → ProgressBar: "Searching..."
    ├─ search_result      → KnowledgeList: append guide
    ├─ generating_report  → ProgressBar: "Generating..."
    ├─ llm_token          → ReportStream: append token
    ├─ report_complete    → ReportViewer: render report_data + link to HTML
    └─ error              → ErrorAlert: show error message
```

---

## UI Design

### Layout: 3-Zone Split

```
┌──────────────────────────────────────────────────────┐
│  [Header] JCL Job Failure Diagnosis                  │
├──────────────────────────────────────────────────────┤
│                                                       │
│  Zone 1: Upload Area (drag & drop + file picker)     │
│  ┌─────────────────────────────────────────────┐     │
│  │  📁 Drop JOB output zip file here           │     │
│  │     or click to browse                       │     │
│  │  [Language: ja ▼]  [Message: ________]       │     │
│  │              [🔍 Analyze]                    │     │
│  └─────────────────────────────────────────────┘     │
│                                                       │
│  Zone 2: Progress Pipeline (SSE events)              │
│  ┌─────────────────────────────────────────────┐     │
│  │ ① Extract ✅ → ② Parse ✅ → ③ Diagnose 🔄  │     │
│  │ → ④ Search ⏳ → ⑤ Report ⏳                 │     │
│  │                                               │     │
│  │ [File List]  [Step Flow]  [Error Details]     │     │
│  └─────────────────────────────────────────────┘     │
│                                                       │
│  Zone 3: Report Viewer                               │
│  ┌─────────────────────────────────────────────┐     │
│  │ [LLM streaming text...]                      │     │
│  │                                               │     │
│  │ [📄 Open Full Report] [📥 Download HTML]     │     │
│  └─────────────────────────────────────────────┘     │
│                                                       │
└──────────────────────────────────────────────────────┘
```

---

## SSE Event Types & UI Mapping

| Event Type | Backend Payload | UI Component | Visual |
|------------|----------------|--------------|--------|
| `file_extracted` | `{message, diagnosis_id}` | ProgressStep ① | Spinner → check |
| `file_classified` | `{total_files, jcl, proc, jesmsg, sysmsg, sysprint, unknown, files[]}` | FileClassification panel | File count badges by type |
| `jcl_parsed` | `{job_name, total_steps, steps[{name,pgm,proc}]}` | JobInfo header | JOB name + step count |
| `step_flow` | `{steps[{step_number, step_name, program, status, return_code}]}` | StepFlowDiagram | Horizontal pipeline with status colors |
| `error_found` | `{code, type, severity, failed_step, message, step_results}` | ErrorCard | Severity badge (CRITICAL=red, HIGH=orange, MEDIUM=yellow) |
| `searching_knowledge` | `{phase, query}` | ProgressStep ④ | Spinner + query text |
| `search_result` | `{source, code, confidence, description}` | KnowledgeGuide item | Confidence bar + source link |
| `generating_report` | `{phase}` | ProgressStep ⑤ | Spinner |
| `llm_token` | `{token}` | ReportStream | Append token (streaming text) |
| `report_complete` | `{diagnosis_id, job_name, severity, primary_error, report_data}` | ReportComplete | Full report_data rendering + action buttons |
| `error` | `{message, diagnosis_id}` | ErrorAlert | Red banner with error message |

---

## Files to Create

| # | File | Purpose | Est. Lines |
|---|------|---------|-----------|
| 1 | `kms-portal-ui/src/api/jcl-diagnosis.api.ts` | API client (SSE fetch + report GET) | ~60 |
| 2 | `kms-portal-ui/src/pages/JCLDiagnosisPage.tsx` | Main page component | ~350 |
| 3 | `kms-portal-ui/src/pages/JCLDiagnosisPage.css` | Page styling (CSS variables, dark mode) | ~250 |

## Files to Modify

| # | File | Change |
|---|------|--------|
| 4 | `kms-portal-ui/src/App.tsx` | Add route: `/jcl-diagnosis` → `JCLDiagnosisPage` |
| 5 | `kms-portal-ui/src/components/Sidebar.tsx` | Add nav item with icon |
| 6 | `kms-portal-ui/src/i18n/locales/ja/common.json` | Add `jclDiagnosis.*` keys (~25 keys) |
| 7 | `kms-portal-ui/src/i18n/locales/ko/common.json` | Add `jclDiagnosis.*` keys (~25 keys) |
| 8 | `kms-portal-ui/src/i18n/locales/en/common.json` | Add `jclDiagnosis.*` keys (~25 keys) |

---

## Implementation Steps

### Step 1: API Client (`jcl-diagnosis.api.ts`)

```typescript
// Types
interface DiagnosisEvent {
  type: string;
  [key: string]: any;
}

// SSE streaming via fetch + ReadableStream
export async function streamDiagnosis(
  file: File, language: string, message?: string,
  onEvent: (event: DiagnosisEvent) => void
): Promise<void>

// Report HTML fetch
export async function getReportUrl(diagnosisId: string): string
```

Key details:
- Use `fetch()` with `ReadableStream` for SSE (not EventSource — POST body needed)
- Parse `data: {...}\n\n` lines from stream
- Include `Authorization: Bearer` header from auth store
- `getReportUrl()` returns URL string for iframe/new-tab (not fetching HTML content)

### Step 2: i18n Keys (3 locales)

Add `jclDiagnosis` namespace with ~25 keys:

```json
{
  "jclDiagnosis": {
    "title": "JCL Job障害診断",
    "nav": "JCL診断",
    "uploadTitle": "JOBスプールファイルをアップロード",
    "uploadHint": "JOB出力のzipファイルをドラッグ＆ドロップ、またはクリックして選択",
    "language": "応答言語",
    "message": "追加質問（任意）",
    "messagePlaceholder": "エラーの詳細や確認したい内容...",
    "analyze": "診断開始",
    "analyzing": "診断中...",
    "phaseExtract": "ファイル解凍",
    "phaseClassify": "ファイル分類",
    "phaseParse": "JCL解析",
    "phaseDiagnose": "エラー診断",
    "phaseSearch": "知識検索",
    "phaseReport": "レポート生成",
    "jobName": "ジョブ名",
    "totalSteps": "ステップ数",
    "errorCode": "エラーコード",
    "severity": "重大度",
    "openReport": "レポートを開く",
    "downloadReport": "HTMLダウンロード",
    "newDiagnosis": "新しい診断",
    "noFileSelected": "ファイルが選択されていません",
    "zipOnly": "zipファイルのみ対応"
  }
}
```

Must add equivalent keys in `en` and `ko` locales.

### Step 3: Main Page Component (`JCLDiagnosisPage.tsx`)

State management:
```typescript
type DiagnosisPhase = 'idle' | 'extracting' | 'classifying' | 'parsing' |
  'diagnosing' | 'searching' | 'generating' | 'complete' | 'error';

interface DiagnosisState {
  phase: DiagnosisPhase;
  diagnosisId: string | null;
  files: { filename: string; type: string }[];
  jobName: string | null;
  steps: StepInfo[];
  error: ErrorInfo | null;
  searchResults: SearchResult[];
  reportText: string;
  reportData: any | null;
  severity: string | null;
}
```

Component structure (inline, no separate component files):
```
JCLDiagnosisPage
├── UploadZone          — drag & drop area, file input, language select, message input
├── ProgressPipeline    — 6 phase steps with status indicators
├── FileClassification  — file type breakdown (shown after file_classified)
├── StepFlowDiagram     — horizontal step pipeline with status colors
├── ErrorCard           — error code, type, severity badge, failed step
├── KnowledgeResults    — search result cards with confidence bars
├── ReportStream        — streaming LLM text output
└── ReportActions       — "Open Report" (new tab) + "Download HTML" buttons
```

All sub-components are sections within the single page file (no separate component files needed).

### Step 4: Page Styling (`JCLDiagnosisPage.css`)

Key styling requirements:
- Use CSS variables from `themes.css` (dark mode support)
- Upload area: dashed border, drag-over highlight
- Progress pipeline: horizontal stepper with connecting lines
- Step flow diagram: colored status indicators (green=COMPLETED, red=ABEND, gray=SKIPPED)
- Error card: severity-colored left border
- Report text: monospace streaming area with auto-scroll
- Responsive: stack vertically on narrow screens
- Print: hide upload zone and progress, show report only

### Step 5: Route Registration (`App.tsx`)

Add lazy-loaded route:
```tsx
const JCLDiagnosisPage = lazy(() => import('./pages/JCLDiagnosisPage'));
// In Routes:
<Route path="/jcl-diagnosis" element={<JCLDiagnosisPage />} />
```

### Step 6: Sidebar Navigation (`Sidebar.tsx`)

Add nav item after "Legacy Modernization":
```typescript
{
  id: 'jclDiagnosis',
  path: '/jcl-diagnosis',
  icon: <FileWarning size={20} />,  // lucide-react
  labelKey: 'jclDiagnosis.nav',
}
```

---

## Key Design Decisions

1. **Single page file**: All sub-sections inline in `JCLDiagnosisPage.tsx` (no separate component files). The page is self-contained and doesn't share components with other pages.

2. **fetch + ReadableStream for SSE**: Cannot use `EventSource` because the endpoint requires `POST` with `multipart/form-data`. Use `fetch()` with `response.body.getReader()`.

3. **Report in new tab**: The full HTML report opens in a new browser tab via `window.open('/api/v1/jcl-diagnosis/{id}/report')`. Not embedded in an iframe.

4. **No Zustand store**: Page state managed with `useState`/`useReducer` within the component. No global store needed — diagnosis is a single-session workflow.

5. **Streaming text display**: LLM tokens accumulated in state string, displayed in a `<pre>` block with auto-scroll to bottom. Markdown rendering optional (plain text sufficient).

---

## Verification Criteria

1. **Upload flow**: Select zip → click Analyze → SSE stream starts → all 6 phases animate
2. **File classification**: After `file_classified` event, file type counts display correctly
3. **Step flow**: After `step_flow` event, horizontal pipeline shows with correct colors
4. **Error display**: After `error_found` event, error code and severity badge appear
5. **LLM streaming**: Tokens appear in real-time in report area
6. **Report complete**: "Open Report" button opens full HTML report in new tab
7. **Error handling**: Pipeline error shows red alert banner
8. **i18n**: All text changes correctly when language is switched (ja/ko/en)
9. **Dark mode**: All colors use CSS variables, no hardcoded colors
10. **Drag & drop**: File drag-over highlights upload area, drop triggers file selection
