# Gap Detector Agent Memory

## Analysis Index

See `analysis-history.md` for detailed older entries (pre-2026-02-25).

| Feature | Date | Type | Rate | Analysis File |
|---------|------|------|:----:|---------------|
| parallel-orchestrator-dag | 02-17 | Design-Impl | 80.8% | `docs/03-analysis/parallel-orchestrator-dag.analysis.md` |
| enterprise-legacy-modernization | 02-18 | Plan-Design | 100% | `docs/03-analysis/enterprise-legacy-modernization.analysis.md` |
| version-specific-parser | 02-18 | Design-Impl | 96% | `docs/03-analysis/version-specific-parser.analysis.md` |
| legacy-host-openframe-agents | 02-18 | Plan-Impl | 97% | `docs/03-analysis/legacy-host-openframe-agents.analysis.md` |
| legacy-modernization-analysis-ui | 02-19 | Design-Impl | 98% | `docs/03-analysis/legacy-modernization-analysis-ui.analysis.md` |
| vllm-hybrid-search-artifact-view | 02-19 | Plan-Impl | 97% | `docs/03-analysis/vllm-hybrid-search-artifact-view.analysis.md` |
| xsp-parser-faithful-wrapper | 02-19 | Plan-Impl | 100% | `docs/03-analysis/xsp-parser-faithful-wrapper.analysis.md` |
| rag-context-pollution-fix | 02-20 | Design-Impl | 92% | `docs/03-analysis/rag-context-pollution-fix.analysis.md` |
| manual-reextraction-training-pipeline | 02-21 | Plan-Impl | 71% | `docs/03-analysis/manual-reextraction-training-pipeline.analysis.md` |
| unified-lora-dataset | 02-22 | Design-Impl | 97% | `docs/03-analysis/unified-lora-dataset.analysis.md` |
| unified-lora-dataset-v2 | 02-22 | Design-Impl | 97% | `docs/03-analysis/unified-lora-dataset-v2.analysis.md` |
| qwen3-dataset-pipeline | 02-24 | Design-Impl | 96% | `docs/03-analysis/qwen3-dataset-pipeline.analysis.md` |
| jcl-job-failure-diagnosis | 02-25 | Design-Impl | 98% | `docs/03-analysis/jcl-job-failure-diagnosis.analysis.md` |
| jcl-diagnosis-report-template | 02-25 | Plan-Impl | 100% | `docs/03-analysis/jcl-diagnosis-report-template.analysis.md` |
| **jcl-diagnosis-frontend-viewer** | **02-25** | **Plan-Impl** | **98%** | **`docs/03-analysis/jcl-diagnosis-frontend-viewer.analysis.md`** |

## Recent Analyses (Details)

### jcl-diagnosis-frontend-viewer (2026-02-25, Plan-vs-Implementation)
- **Match Rate**: 98% (97 items checked, 93 exact, 2 acceptable variations, 2 changed, 0 missing)
- **Analysis Type**: Plan-to-Implementation (8 files: 3 created, 5 modified)
- **Plan**: `docs/01-plan/features/jcl-diagnosis-frontend-viewer.plan.md` (286 lines)
- **Analysis**: `docs/03-analysis/jcl-diagnosis-frontend-viewer.analysis.md` (v1.0)
- **Key Files**: `jcl-diagnosis.api.ts` (75 lines), `JCLDiagnosisPage.tsx` (643 lines), `JCLDiagnosisPage.css` (651 lines)
- **All 11 SSE events handled**: file_extracted, file_classified, jcl_parsed, step_flow, error_found, searching_knowledge, search_result, generating_report, llm_token, report_complete, error
- **All 3 UI zones**: Upload (drag&drop+file+lang+msg), Progress Pipeline (6 phases), Report Viewer (stream+actions)
- **i18n**: 25 keys in all 3 locales (ja/ko/en), exact match to plan's example JSON
- **Changed**: (1) Static import vs plan's lazy() -- consistent with all other pages in App.tsx, (2) `#eab308` hardcoded for severity-medium -- no CSS variable exists
- **Acceptable**: (1) `credentials: 'include'` vs Bearer header (HttpOnly cookie auth project convention), (2) `common.nav.jclDiagnosis` vs `jclDiagnosis.nav` (project nav namespace convention)
- **11 additive enhancements**: AbortSignal, fileStats, totalSteps, errorMessage, handleReset, download HTML, file size display, PHASES config, LOW severity, spin animation, classifying phase
- **Pattern**: Frontend SSE via `fetch()` + `getReader()` (not EventSource) for POST multipart -- same as backend's SSE pattern
- **Pattern**: `credentials: 'include'` for HttpOnly cookie auth -- project convention, NOT Bearer token
- **Gotcha**: App.tsx uses static imports for ALL pages (no lazy loading) -- plan suggesting `lazy()` was aspirational, not project convention

### jcl-job-failure-diagnosis (2026-02-25, Design-vs-Implementation)
- **Match Rate**: 98% (129 items checked, 115 exact, 11 acceptable, 3 changed, 0 missing)
- **Analysis**: `docs/03-analysis/jcl-job-failure-diagnosis.analysis.md` (v1.0)
- **Architecture**: 5-agent pipeline (FileProcessor->JCLAnalyzer->ErrorDiagnosis->KnowledgeRetriever->ReportGenerator)
- **Pattern**: `LearningLLMService.generate_stream(question=, context=, product=)` -- not `stream_generate(prompt=)`
- **Pattern**: Singleton via `_instance` + `get_jcl_diagnosis_orchestrator()` (project convention)

### jcl-diagnosis-report-template (2026-02-25, Plan-vs-Implementation)
- **Match Rate**: 100% (44 items checked, 44 exact, 0 gaps)
- **Analysis**: `docs/03-analysis/jcl-diagnosis-report-template.analysis.md` (v1.0)
- **Pattern**: Self-contained HTML with no Jinja2 -- all rendering via JS in browser

## Common Patterns
- Backend service: singleton via `_instance` + `get_*()` factory
- Frontend SSE: `fetch()` + `getReader()` for POST multipart; `EventSource` for GET-only SSE
- Frontend auth: `credentials: 'include'` (HttpOnly cookies), NOT `Authorization: Bearer` header
- Frontend nav: all sidebar labelKeys use `common.nav.*` namespace
- Frontend routing: static imports (no `lazy()`), all pages imported directly in App.tsx
- SSE envelope: `data: {"type": "event_name", ...}\n\n`
- i18n: always update all 3 locales (en/ko/ja) with identical key sets
- CSS: use `var(--color-*)` from themes.css for dark mode support

## Critical Bugs Found (Across All Analyses)
- `vllm-hybrid-search-artifact-view`: `from ..core.config import settings` fails -- use `api_settings`
- `unified-lora-dataset`: `main.py:459` passes Path instead of ProcessorConfig
- `qwen3-dataset-pipeline`: Dedup-before-scale amplifies category imbalance
