# Plan: JCL Diagnosis Report Templateization

> **Feature**: `jcl-diagnosis-report-template`
> **Created**: 2026-02-25
> **Priority**: High
> **Level**: Enterprise

---

## Context

The JCL Diagnosis Agent (5-agent pipeline) currently produces **plain text markdown** via LLM streaming. There is no structured HTML report output. Two prototype files already exist:

- `jcl_diagnosis_report.html` (901 lines) — self-contained HTML with warm earth-tone design, 7 sections, markdown export, print styles
- `report_schema.json` (155 lines) — JSON data contract for report content

**Goal**: Formalize the data/presentation separation, create a reusable backend service that converts `DiagnosisReport` (Pydantic) → report schema JSON → self-contained HTML, renderable in any browser.

---

## Architecture

```
[5-Agent Pipeline completes]
       ↓
  DiagnosisReport (Pydantic)
       ↓
  HTMLReportService._convert_to_report_schema()  →  report_schema JSON
       ↓
  HTMLReportService.render()  →  Inject JSON + LABELS into HTML template
       ↓
  Self-contained .html file  →  Browser / Claude Code playground
```

**Design Decision**: Self-contained HTML with JS rendering (Option C). No Jinja2 or extra dependencies. Template uses `__REPORT_DATA_PLACEHOLDER__` and `__LABELS_PLACEHOLDER__` replaced by Python `str.replace()`.

---

## Files to Create

| # | File | Purpose |
|---|------|---------|
| 1 | `app/api/services/jcl_diagnosis/templates/diagnosis_report.html` | Parameterized HTML template (from existing prototype) |
| 2 | `app/api/services/jcl_diagnosis/report_template.py` | `HTMLReportService` — schema conversion + HTML rendering |
| 3 | `app/api/services/jcl_diagnosis/locales.py` | i18n label maps (ja/ko/en) for template UI strings |

## Files to Modify

| # | File | Change |
|---|------|--------|
| 4 | `app/api/models/jcl_diagnosis.py` | Add `report_html: str` and `report_data: Optional[Dict]` to `DiagnosisReport` |
| 5 | `app/api/services/jcl_diagnosis/orchestrator.py` | Accumulate LLM tokens → build `DiagnosisReport` → call `HTMLReportService.render()` → include in `report_complete` event |
| 6 | `app/api/routers/jcl_diagnosis.py` | Add `GET /{diagnosis_id}/report` endpoint returning `HTMLResponse` |
| 7 | `app/api/services/jcl_diagnosis/__init__.py` | Export `HTMLReportService`, `get_html_report_service` |

---

## Implementation Steps

### Step 1: Localization module (`locales.py`)

Create `LABELS` dict keyed by `ja`/`ko`/`en` containing all UI strings used in the HTML template: section headers, button labels, severity names, status labels, date format locale codes.

All 3 locale dicts must have identical key sets. The template JS code references `LABELS.section_job_summary`, `LABELS.label_copy`, etc.

### Step 2: Parameterize HTML template (`templates/diagnosis_report.html`)

Take existing `jcl_diagnosis_report.html` and:
1. Replace `const REPORT_DATA = {...};` → `const REPORT_DATA = __REPORT_DATA_PLACEHOLDER__;`
2. Add `const LABELS = __LABELS_PLACEHOLDER__;`
3. Replace all hardcoded Japanese strings in render functions with `LABELS.*` references
4. Replace `'ja-JP'` in date formatting with `LABELS.locale_code`
5. Create `templates/` directory under `services/jcl_diagnosis/`

### Step 3: `HTMLReportService` (`report_template.py`)

Core service with:
- **`render(report: DiagnosisReport) -> str`** — main entry point, returns complete HTML
- **`_convert_to_report_schema(report) -> Dict`** — Pydantic → JSON schema conversion
- **`_load_template() -> str`** — file read with caching
- Singleton pattern: `get_html_report_service()`

**Schema Conversion Mapping** (key transformations):

| Report Schema Field | Pydantic Source | Transform |
|---------------------|-----------------|-----------|
| `job_summary.*` | `JobAnalysis` | Direct mapping + computed `completed_steps` |
| `step_flow[].status` | `JobStep.status: StepStatus` | Map: NORMAL/WARNING→"COMPLETED", ABEND_*→"ABEND", SKIPPED/NOT_RUN→"SKIPPED" |
| `step_flow[].input_datasets` | `JobStep.dd_statements` | Filter by DISP containing OLD/SHR |
| `step_flow[].output_datasets` | `JobStep.dd_statements` | Filter by DISP containing NEW/OUT/MOD |
| `error_diagnosis.error_category` | `ABEND_REGISTRY[code]["description"]` | Lookup from existing registry |
| `error_diagnosis.root_cause_analysis` | `DiagnosisReport.report_text` | LLM-generated text |
| `resolutions[]` | `KnowledgeResult.error_guides` | confidence→priority mapping (>0.9=HIGH, >0.5=MEDIUM, else LOW) |
| `similar_cases[]` | `KnowledgeResult.similar_cases` | Direct mapping with generated case_id |

### Step 4: Extend `DiagnosisReport` model

Add to `models/jcl_diagnosis.py`:
```python
report_html: str = Field(default="", description="Rendered HTML report")
report_data: Optional[Dict] = Field(default=None, description="Structured report JSON")
```

### Step 5: Integrate into Orchestrator

Modify `orchestrator.py:stream_diagnosis()`:
1. Accumulate LLM tokens during `report_generator.stream_report()` loop
2. After streaming completes, build full `DiagnosisReport`
3. Call `get_html_report_service().render(report)`
4. Include `report_data` (JSON) in `report_complete` SSE event
5. Store `report_html` in in-memory cache (keyed by `diagnosis_id`)

**Note**: Send `report_data` (JSON, ~3KB) via SSE, NOT `report_html` (~40KB). HTML retrieved via dedicated endpoint.

### Step 6: Add HTML report endpoint

Add to `routers/jcl_diagnosis.py`:
```
GET /api/v1/jcl-diagnosis/{diagnosis_id}/report → HTMLResponse
```
- Reads from in-memory cache (TTL-based, 1 hour)
- Returns self-contained HTML with `Content-Type: text/html`
- 404 if report not found or expired

### Step 7: Update exports

Add `HTMLReportService` and `get_html_report_service` to `__init__.py`.

---

## Key Reusable Assets

| Asset | Location | Usage |
|-------|----------|-------|
| Existing HTML prototype | `jcl_diagnosis_report.html` | Source for parameterized template (CSS, JS, render functions) |
| JSON schema contract | `report_schema.json` | Target format for schema conversion |
| ABEND registry | `services/jcl_diagnosis/abend_code_registry.py` | Error category lookup |
| Service singleton pattern | All services in `app/api/services/` | `_instance` + `get_*()` factory |
| DiagnosisReport model | `models/jcl_diagnosis.py` | Input data structure |
| StepStatus enum | `models/jcl_diagnosis.py` | Step status mapping source |

---

## Verification

1. **Unit test**: Create `DiagnosisReport` with sample data → call `render()` → verify HTML contains job name, no placeholders remain, valid `<!DOCTYPE html>`
2. **Schema test**: Verify each `StepStatus` maps correctly, null fields handled gracefully
3. **Locale test**: Verify ja/ko/en label dicts have identical key sets
4. **Browser test**: Open rendered HTML in browser → verify all 7 sections render, code copy works, markdown export works, print layout correct
5. **Integration test**: Run full pipeline with sample zip → verify `report_complete` SSE event contains `report_data` → hit GET endpoint → verify HTML response
